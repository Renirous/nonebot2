import os
import re
from functools import reduce

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ProcessPoolExecutor
from apscheduler.jobstores.base import JobLookupError

from command import CommandRegistry, hub as cmdhub
from commands import core
from little_shit import get_db_dir, get_command_args_start_flags, get_target

_db_url = 'sqlite:///' + os.path.join(get_db_dir(), 'scheduler.sqlite')

_scheduler = BackgroundScheduler(
    jobstores={
        'default': SQLAlchemyJobStore(url=_db_url)
    },
    executors={
        'default': ProcessPoolExecutor(max_workers=2)
    },
    timezone=pytz.timezone('Asia/Shanghai')
)

_command_args_start_flags = get_command_args_start_flags()

_args_split_sep = '[ \n\t]'


def _init():
    _scheduler.start()


__registry__ = cr = CommandRegistry(init_func=_init)


class _InvalidTriggerArgsError(Exception):
    pass


class _IncompleteArgsError(Exception):
    pass


def _call_commands(command_list, ctx_msg):
    print('Doing jobs: ', command_list)
    for command in command_list:
        cmdhub.call(command[0], command[1], ctx_msg)


@cr.register('add_job', 'add-job', 'add')
@cr.restrict(full_command_only=True, group_admin_only=True)
def add_job(args_text, ctx_msg, internal=False):
    if args_text.strip() in ('', 'help', '-h', '--help') and not internal:
        _send_add_job_help_msg(ctx_msg, internal)

    args_text = args_text.lstrip()
    try:
        # Parse trigger args
        trigger_args = {}
        if args_text.startswith('-'):
            # options mode
            key_dict = {
                '-M': 'minute',
                '-H': 'hour',
                '-d': 'day',
                '-m': 'month',
                '-w': 'day_of_week'
            }
            while args_text.startswith('-') and not args_text.startswith('--'):
                try:
                    option, value, args_text = re.split(_args_split_sep, args_text, 2)
                    trigger_args[key_dict[option]] = value
                    args_text = args_text.lstrip()
                except (ValueError, KeyError):
                    # Split failed or get key failed, which means format is not correct
                    raise _InvalidTriggerArgsError
        else:
            # cron mode
            try:
                trigger_args['minute'], \
                trigger_args['hour'], \
                trigger_args['day'], \
                trigger_args['month'], \
                trigger_args['day_of_week'], \
                args_text = re.split(_args_split_sep, args_text, 5)
                args_text = args_text.lstrip()
            except ValueError:
                # Split failed, which means format is not correct
                raise _InvalidTriggerArgsError

        # Parse '--multi' option
        multi = False
        if args_text.startswith('--multi '):
            multi = True
            tmp = re.split(_args_split_sep, args_text, 1)
            if len(tmp) < 2:
                raise _IncompleteArgsError
            args_text = tmp[1].lstrip()

        tmp = re.split(_args_split_sep, args_text, 1)
        if len(tmp) < 2:
            raise _IncompleteArgsError
        job_id_without_suffix, command_raw = tmp
        job_id = job_id_without_suffix + '_' + get_target(ctx_msg)
        command_list = []
        if multi:
            command_raw_list = command_raw.split('\n')
            for cmd_raw in command_raw_list:
                cmd_raw = cmd_raw.lstrip()
                if not cmd_raw:
                    continue
                tmp = re.split('|'.join(_command_args_start_flags), cmd_raw, 1)
                if len(tmp) < 2:
                    tmp.append('')
                command_list.append(tuple(tmp))
        else:
            command_raw = command_raw.lstrip()
            tmp = re.split('|'.join(_command_args_start_flags), command_raw, 1)
            if len(tmp) < 2:
                tmp.append('')
            command_list.append(tuple(tmp))

        job_args = {'command_list': command_list, 'ctx_msg': ctx_msg}
        job = _scheduler.add_job(_call_commands, kwargs=job_args, trigger='cron', **trigger_args,
                                 id=job_id, replace_existing=True, misfire_grace_time=30)
        _send_text('成功添加计划任务，ID：' + job_id_without_suffix, ctx_msg, internal)
        return job
    except _InvalidTriggerArgsError:
        _send_add_job_trigger_args_invalid_msg(ctx_msg, internal)
    except _IncompleteArgsError:
        _send_add_job_incomplete_args_msg(ctx_msg, internal)


@cr.register('remove_job', 'remove-job', 'remove')
@cr.restrict(full_command_only=True, group_admin_only=True)
def remove_job(args_text, ctx_msg, internal=False):
    job_id_without_suffix = args_text.strip()
    job_id = job_id_without_suffix + '_' + get_target(ctx_msg)
    try:
        _scheduler.remove_job(job_id, 'default')
        _send_text('成功删除计划任务，ID：' + job_id_without_suffix, ctx_msg, internal)
    except JobLookupError:
        _send_text('没有找到这个 ID 的计划任务', ctx_msg, internal)


@cr.register('list_jobs', 'list-jobs', 'list')
@cr.restrict(full_command_only=True, group_admin_only=True)
def list_jobs(_, ctx_msg, internal=False):
    target = get_target(ctx_msg)
    job_id_suffix = '_' + target
    jobs = list(filter(lambda j: j.id.endswith(job_id_suffix), _scheduler.get_jobs('default')))
    if internal:
        return jobs

    for job in jobs:
        job_id = job.id[:-len(job_id_suffix)]
        command_list = job.kwargs['command_list']
        reply = 'ID：' + job_id + '\n'
        reply += '命令：\n'
        if len(command_list) > 1:
            reply += reduce(lambda x, y: x[0] + ' ' + x[1] + '\n' + y[0] + ' ' + y[1], command_list)
        else:
            reply += command_list[0][0] + ' ' + command_list[0][1]
        core.echo(reply, ctx_msg)
    if len(jobs):
        core.echo('以上', ctx_msg)
    else:
        core.echo('还没有添加计划任务', ctx_msg)


def _send_text(text, ctx_msg, internal):
    if not internal:
        core.echo(text, ctx_msg)


def _send_add_job_help_msg(ctx_msg, internal):
    _send_text(
        '此为高级命令！如果你不知道自己在做什么，请不要使用此命令。\n\n'
        '使用方法：\n'
        '/scheduler.add_job options|cron [--multi] job_id command\n'
        '说明：\n'
        'options 和 cron 用来表示触发参数，有且只能有其一，格式分别如下：\n'
        'options：\n'
        '  -M 分，0 到 59\n'
        '  -H 时，0 到 23\n'
        '  -d 日，1 到 31\n'
        '  -m 月，1 到 12\n'
        '  -w 星期，1 到 7，其中 7 表示星期天\n'
        '  以上选项的值的表示法和下面的 cron 模式相同\n'
        'cron：\n'
        '  此模式和 Linux 的 crontab 文件的格式、顺序相同，一共 5 个用空格隔开的参数\n'
        '\n'
        '剩下三个参数见下一条',
        ctx_msg,
        internal
    )
    core.echo(
        '--multi 为可选项，表示读取多条命令\n'
        'job_id 为必填项，允许使用符合正则 [_\-a-zA-Z0-9] 的字符，作为计划任务的唯一标识\n'
        'command 为必填项，从 job_id 之后第一个非空白字符开始，如果加了 --multi 选项，则每行算一条命令，否则一直到消息结束算作一整条命令（注意这里的命令不要加 / 前缀）\n'
        '\n'
        '例 1：\n'
        '以下命令将添加计划在每天晚上 10 点推送当天的知乎日报，并发送一条鼓励的消息：\n'
        '/scheduler.add_job 0 22 * * * --multi zhihu-daily-job\n'
        'zhihu\n'
        'echo 今天又是很棒的一天哦！\n'
        '例 2：\n'
        '以下命令将每 5 分钟发送一条提示：\n'
        '/scheduler.add_job -M */5 tip-job echo 提示内容',
        ctx_msg
    )


def _send_add_job_trigger_args_invalid_msg(ctx_msg, internal):
    _send_text(
        '触发参数的格式不正确\n'
        '如需帮助，请发送如下命令：\n'
        '/scheduler.add_job --help',
        ctx_msg,
        internal
    )


def _send_add_job_incomplete_args_msg(ctx_msg, internal):
    _send_text(
        '缺少必须的参数\n'
        '如需帮助，请发送如下命令：\n'
        '/scheduler.add_job --help',
        ctx_msg,
        internal
    )
