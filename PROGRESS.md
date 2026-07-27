# 交付进度
- 目标：补齐 LICENSE、真实 CI、演示图、英文入口与中文宣传长图。
- 顺序：基线 → LICENSE → CI → 演示图 → 英文 README → 宣传长图 → 总验收。
- 最大风险：裸 Python 环境不合规，且 `gh` 令牌失效；证据见 BLOCKED.md。
- 约束：只修改任务单允许的文件，每项独立提交并推送 `main`。
- 任务 0：完成；合规 Python 下 59 项测试通过，Skill 校验通过。
- 任务 1：完成；已添加标准 MIT LICENSE 与中文 README License 徽章。
- 决策：CI action 使用官方当前 v6；比旧范例的 v4/v5 更符合 2026 托管 runner。
- 任务 2：第 1 次 CI 为 Ubuntu 全绿、Windows 因 cp1252 中文输出失败。
- 当前：workflow 启用 `PYTHONUTF8=1` 后进行第 2 次 CI 验证。
