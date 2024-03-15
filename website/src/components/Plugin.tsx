import React, { useCallback, useState } from "react";
import { usePagination } from "react-use-pagination";

import plugins from "../../static/plugins.json";
import { useFilteredObjs } from "../libs/store";
import Card from "./Card";
import Modal from "./Modal";
import Paginate from "./Paginate";

export default function Adapter(): JSX.Element {
  const [modalOpen, setModalOpen] = useState<boolean>(false);
  const {
    filter,
    setFilter,
    filteredObjs: filteredPlugins,
  } = useFilteredObjs(plugins);

  const props = usePagination({
    totalItems: filteredPlugins.length,
    initialPageSize: 10,
  });
  const { startIndex, endIndex } = props;
  const currentPlugins = filteredPlugins.slice(startIndex, endIndex + 1);

  const [form, setForm] = useState<{
    name: string;
    desc: string;
    projectLink: string;
    moduleName: string;
    homepage: string;
  }>({ name: "", desc: "", projectLink: "", moduleName: "", homepage: "" });
  const onSubmit = () => {
    console.log(form);
  };
  const onChange = (event) => {
    const target = event.target;
    const value = target.type === "checkbox" ? target.checked : target.value;
    const name = target.name;

    setForm({
      ...form,
      [name]: value,
    });
    event.preventDefault();
  };

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4 px-4">
        <input
          className="w-full px-4 py-2 border rounded-full bg-light-nonepress-100 dark:bg-dark-nonepress-100"
          value={filter}
          placeholder="搜索插件"
          onChange={(event) => setFilter(event.target.value)}
        />
        <button
          className="w-full rounded-lg bg-hero text-white"
          onClick={() => setModalOpen(true)}
        >
          发布插件
        </button>
      </div>
      <div className="grid grid-cols-1 p-4">
        <Paginate {...props} />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 px-4">
        {currentPlugins.map((plugin, index) => (
          <Card key={index} {...plugin} />
        ))}
      </div>
      <div className="grid grid-cols-1 p-4">
        <Paginate {...props} />
      </div>
      <Modal active={modalOpen} setActive={setModalOpen}>
        <div className="w-full max-w-[600px] max-h-[90%] overflow-y-auto rounded shadow-lg m-6 origin-center transition z-[inherit] pointer-events-auto thin-scrollbar">
          <div className="bg-light-nonepress-100 dark:bg-dark-nonepress-100">
            <div className="px-6 pt-4 pb-2 font-medium text-xl">
              <span>插件信息</span>
            </div>
            <div className="px-6 pb-5 w-full">
              <form onSubmit={onSubmit}>
                <div className="grid grid-cols-1 gap-4 p-4">
                  <label className="flex flex-wrap">
                    <span className="mr-2">插件名称:</span>
                    <input
                      type="text"
                      name="name"
                      maxLength={20}
                      className="px-2 flex-grow rounded bg-light-nonepress-200 dark:bg-dark-nonepress-200"
                      onChange={onChange}
                    />
                  </label>
                  <label className="flex flex-wrap">
                    <span className="mr-2">插件介绍:</span>
                    <input
                      type="text"
                      name="desc"
                      className="px-2 flex-grow rounded bg-light-nonepress-200 dark:bg-dark-nonepress-200"
                      onChange={onChange}
                    />
                  </label>
                  <label className="flex flex-wrap">
                    <span className="mr-2">PyPI 项目名:</span>
                    <input
                      type="text"
                      name="projectLink"
                      className="px-2 flex-grow rounded bg-light-nonepress-200 dark:bg-dark-nonepress-200"
                      onChange={onChange}
                    />
                  </label>
                  <label className="flex flex-wrap">
                    <span className="mr-2">import 包名:</span>
                    <input
                      type="text"
                      name="moduleName"
                      className="px-2 flex-grow rounded bg-light-nonepress-200 dark:bg-dark-nonepress-200"
                      onChange={onChange}
                    />
                  </label>
                  <label className="flex flex-wrap">
                    <span className="mr-2">仓库/主页:</span>
                    <input
                      type="text"
                      name="homepage"
                      className="px-2 flex-grow rounded bg-light-nonepress-200 dark:bg-dark-nonepress-200"
                      onChange={onChange}
                    />
                  </label>
                </div>
              </form>
            </div>
            <div className="px-4 py-2 flex justify-end">
              <button className="px-2 h-9 min-w-[64px] rounded text-hero hover:bg-hero hover:bg-opacity-[.08]">
                关闭
              </button>
              <button
                className="ml-2 px-2 h-9 min-w-[64px] rounded text-hero hover:bg-hero hover:bg-opacity-[.08]"
                onClick={onSubmit}
              >
                发布
              </button>
            </div>
          </div>
        </div>
      </Modal>
    </>
  );
}
