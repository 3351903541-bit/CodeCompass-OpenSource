# 第三方来源与许可

仓库根目录的 MIT 许可证仅适用于 CodeCompass 团队自有内容。运行依赖和开源源码快照按下表及各自附带的原始许可使用，不得去掉其版权声明、许可和免责声明。BSD-3-Clause 快照不代表上游为本项目背书。

| 资源 | 固定来源和许可 | 发布方式 |
| --- | --- | --- |
| boltons | [4e5faa3 · BSD-3-Clause](https://github.com/mahmoud/boltons/blob/4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d/LICENSE) | [固定源码及原 LICENSE](benchmarks/sources/boltons/) |
| more-itertools | [4aeb433 · MIT](https://github.com/more-itertools/more-itertools/blob/4aeb4338ae1407d8da9723e86da99efeb446f719/LICENSE) | [固定源码及原 LICENSE](benchmarks/sources/more_itertools_B_D07_v2/) |
| itsdangerous | [672971d · BSD-3-Clause](https://github.com/pallets/itsdangerous/blob/672971d66a2ef9f85151e53283113f33d642dabd/LICENSE.txt) | [固定源码及原 LICENSE.txt](benchmarks/sources/r5-offline/itsdangerous/) |
| schedule | [82a43db · MIT](https://github.com/dbader/schedule/blob/82a43db1b938d8fdf60103bd41f329e06c8d3651/LICENSE.txt) | 只提供快照清单，复现时直接从上游固定提交下载 |
| python-slugify | [35aca63 · MIT](https://github.com/un33k/python-slugify/blob/35aca63fc2672cba2c739ff6dff685a4f26a4f9a/LICENSE) | 只提供快照清单，复现时直接从上游固定提交下载 |

快照仅用于读取和分析；复现不安装这些案例仓库的上游依赖。快照中历史生成的 `license: not_checked` 表示导入程序未自动判断许可证；本表依据对应固定提交和随包许可文件核对，不改写已冻结的输入元数据。重新分发源码时请保留原授权文本。

`dependencies/` 下六个 wheel 的具体版本和下载文件校验值见 [requirements.txt](requirements.txt)，原许可和声明位于各 wheel 的 `.dist-info/` 中。pytest 及其依赖只用于测试，按 [requirements-test.txt](requirements-test.txt) 安装，不随源码包捆绑。GitHub 和 DeepSeek 是外部服务；浏览器和操作系统字体不随包提供。
