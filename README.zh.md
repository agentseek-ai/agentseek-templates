# AgentSeek 模板目录

本仓库是 [AgentSeek](https://github.com/ob-labs/agentseek) 官方、带版本的
lifecycle-v2 模板目录。模板目录发布是 AgentSeek 发布的不可变输入：CLI
按完整提交 SHA 解析模板，不依赖可变分支。

## 使用模板目录

AgentSeek 0.1.x 将本仓库的已审核版本作为内置默认模板目录。如需检查其他
已审核提交或从中创建项目，可显式传入仓库和完整提交 SHA：

```bash
agentseek create --list-templates \
  --template-repo https://github.com/agentseek-ai/agentseek-templates.git \
  --checkout <40-character-commit-sha>

agentseek create bub/default \
  --template-repo https://github.com/agentseek-ai/agentseek-templates.git \
  --checkout <40-character-commit-sha>
```

仓库 URL 与提交 SHA 共同构成唯一坐标，列出、说明与创建模板都使用同一
坐标。显式坐标不可用或无效时，AgentSeek 不会静默回退。

## 仓库约定

- `templates/index.json` 是模板注册表的唯一事实来源。
- 每个已注册的 `templates/<type>/<name>` 子树都必须自包含，并能生成严格
  lifecycle-v2 项目。
- `catalog-origin.json` 记录导入所用的 core 提交、注册表摘要、纳入模板和有
  意排除项。
- 生成项目中的 Git 依赖固定到 core AgentSeek 仓库的完整提交，绝不指向本
  模板目录仓库。
- lifecycle-v1 兼容镜像继续保留在 core 仓库，供 AgentSeek 0.0.x 使用；后
  续模板目录变更应在本仓库完成。

修改注册表或模板前，请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

Apache License 2.0，详见 [LICENSE](LICENSE)。
