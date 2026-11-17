# CodeCompass

CodeCompass 将学习目标映射到真实开源源码，根据学习者画像组织阅读材料和顺序，并提供源码导读、反馈重规划及 Issue 实践准备。

## 快速开始

1. 安装 Windows x64 版 Python 3.12。从 [Release](https://github.com/3351903541-bit/CodeCompass-OpenSource/releases/tag/v2026.11.17-competition) 下载 `CodeCompass-v2026.11.17-competition.zip` 并完整解压至可写目录，或执行 `git clone https://github.com/3351903541-bit/CodeCompass-OpenSource.git`。
2. 双击 `启动.cmd`，或运行 `powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/start_product.ps1 -Port 8789`。首次启动创建虚拟环境，并从包内安装校验过的运行依赖。
3. 在 Edge 或 Chrome 打开 <http://127.0.0.1:8789/>。如有端口冲突可修改端口参数。学习数据保存在本机 `local_data/`。

**最小案例。** 点击「建立我的能力画像」，完成经验调查，保存或跳过测评。导入 `https://github.com/pallets/itsdangerous`，选择「解码编码后的文本」相关实现并生成路线。在源码研读页打开导读，完成一个步骤并查看剩余路线。页面导入使用当时的公开提交；要用固定版本对照，执行下方复现命令。

**不需要模型密钥。** 目标定位、规划、源码导读、主题复核和反馈重规划都有本地路径。动态导入和刷新 Issue 需要联网。若自愿启用 DeepSeek，可在启动服务的 PowerShell 会话中设置 `DEEPSEEK_API_KEY`，或使用设置页。模型请求可能发送问题、目标、公开仓库与源码定位信息、所选片段、相关对话和有限的学习主题或能力摘要。请勿输入个人信息或私有代码。

## 测试和复用

先启动一次安装运行依赖，再在项目根目录执行：

~~~powershell
$py = '.\.venv\Scripts\python.exe'
& $py -m pip install -r requirements-test.txt
& $py -m pytest tests/product
~~~

[四仓案例和反馈边界复现](reproduction/README.md)提供命令、固定源码、预期结果和 JSON 证据路径。工程用例不能证明真人学习效果。

| 场景 | 入口 |
| --- | --- |
| 源码导入、AST 与调用关系 | [repositories.py](src/codecompass/product/repositories.py)、[源码图层](src/codecompass/graph/)、[call_resolution.py](src/codecompass/product/call_resolution.py) |
| 目标定位与材料检索 | [goal_resolution.py](src/codecompass/product/goal_resolution.py)、[source_routes.py](src/codecompass/product/source_routes.py)、[检索模块](src/codecompass/retrieval/) |
| 材料选择、知识供应、排序、反馈 | [adaptive.py](src/codecompass/planner/adaptive.py)、[reading_order.py](src/codecompass/product/reading_order.py)、[workspaces.py](src/codecompass/product/workspaces.py) |
| 问答、Issue 准备、持久化 | [source_assistant.py](src/codecompass/product/source_assistant.py)、[source_issues.py](src/codecompass/product/source_issues.py)、[store.py](src/codecompass/product/store.py) |

复用时可参考复现脚本的 `acquire → enrich → build → solve → optimize_first_order` 调用链。产品实现来自比赛定稿 `02798b4367ab18300ea80daea40fe5a762f4ff10`；此版本沿用比赛运行包的资源范围，并补充公开验证材料。

## 限制、授权与反馈

当前支持符合规模和文件限制的公开 Python 仓库。静态分析不能确认全部动态绑定；阅读成本是相对指标，有界搜索不保证全局最优。Issue 关联供调查准备。问题可通过 [GitHub Issues](https://github.com/3351903541-bit/CodeCompass-OpenSource/issues) 提交；维护将优先处理安装和复现问题，见[贡献说明](CONTRIBUTING.md)。

[MIT](LICENSE)只适用于团队自有内容。第三方快照和依赖遵循各自的[许可、版权声明及来源说明](THIRD_PARTY.md)。
