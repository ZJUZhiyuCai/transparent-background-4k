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

