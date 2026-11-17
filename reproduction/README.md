# 固定源码和反馈复现

先按 README 启动一次以安装依赖，再关闭服务。在公开版根目录执行。无需模型密钥。第一步访问固定上游源码，后两步使用固定输入、本机临时数据库和回环接口。

~~~powershell
$py = '.\.venv\Scripts\python.exe'
$out = '.\tmp\reproduction'
& $py reproduction/get_review_snapshots.py --manifests reproduction/source-manifests.json --output "$out/snapshots"
& $py reproduction/verify_four_final.py --product . --cache "$out/snapshots" --freeze-reference reproduction/freeze-reference.json --output "$out/four/results.json"
& $py reproduction/verify_freeze_boundary.py --root . --cache "$out/snapshots" --helpers reproduction --output "$out/boundary"
~~~

- `source-manifests.json` 记录来源、固定提交和逐文件 SHA-256。正式加载器同时核对清单哈希、文件长度和 Git blob。boltons、itsdangerous 使用附原许可证的包内固定文件；下载缓存不应提交。
- `four/results.json` 记录候选、选集、最终顺序、目标覆盖和预算审计，与 `freeze-reference.json` 对照。预期选中单元数为 3、8、4、6，J 为 37.4665、67.967、41.956125、46.959875，顺序是 python-slugify、schedule、boltons、itsdangerous。
- `boundary/freeze_boundary_verification.json` 及 T1–T5 日志分别验证反馈、逆序参考校正、构造历史跳步、紧预算回退、请求重放和重启恢复。源码是真实固定快照，反馈由程序提交；T2–T4 的特定输入是探针，不是用户试验。
- Issue 历史匹配与刷新失效使用显式合成夹具；模型接口测试使用模拟传输。它们不证明在线模型质量、Issue 实时状态或真人学习效果。
