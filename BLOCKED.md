# 待裁决清单

## 2026-07-27：任务 0 基线环境存在两项偏差

1. 裸 `python3` 实际指向 Apple Command Line Tools Python 3.9，执行
   `python3 -B -m unittest discover -s tests` 仅发现 8 项测试，并因
   `ModuleNotFoundError: No module named 'numpy'` 出现 4 failures、2 errors。
   使用符合项目要求的 `/opt/homebrew/bin/python3`（Python 3.14.4，
   Pillow 12.2.0、numpy 2.4.6）复跑得到 `Ran 59 tests in 0.655s`、`OK`。
2. `gh auth status` 显示账号 `ZJUZhiyuCai` 的默认令牌无效，与任务单记录的
   “已登录”不一致。Git SSH 推送此前可用；CI 查询与 `gh run watch` 仍需重新认证，
   或改用只读 GitHub 接口取得等价证据。

以上均为本机环境偏差，未发现仓库代码回归；不修改依赖或判卷文件。

## 2026-07-27：默认 Windows 控制台编码会使中文路径 CLI 测试失败

- CI run `30282780510`：Ubuntu × Python 3.10/3.12 通过；Windows 两项均失败。
- 两个 Windows job 都运行了 59 项测试，唯一失败为
  `test_cli_subprocess_handles_spaces_and_unicode_paths`。
- 根因：`scripts/make_transparent_4k.py` 输出中文路径时，Windows runner 的
  `cp1252` stdout 抛出 `UnicodeEncodeError`。
- CI 处理：在 workflow 设置 `PYTHONUTF8=1` 后重试，验证项目在 UTF-8
  Windows 环境的承诺。
- 待裁决：脚本是否应主动配置 UTF-8 或安全降级输出。任务边界禁止修改
  `scripts/`，因此本次不修实现，只保留风险说明。
