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

## Catalog 元数据职责

| 文件 | 职责 | 拉取模板时是否使用 |
| --- | --- | --- |
| `templates/index.json` | 当前 catalog 提交所发布模板的唯一注册表。 | 使用。显式 catalog 坐标会直接读取它；默认锁定路径会将下载内容与内置快照进行校验。 |
| `catalog-origin.json` | 首次从 core 仓库导入时形成的不可变审计记录；后续在 catalog 中原生新增的模板不加入这份导入清单。 | 不使用。 |
| `catalog-release.json` | 供发布与仓库检查使用的 catalog 版本、lifecycle 版本和配套 core 版本坐标。 | 不使用。 |
| AgentSeek `catalog-lock.json` | 内置在 AgentSeek 包中的运行时锁文件，固定 catalog 仓库与提交，并保存注册表快照和每个模板的摘要。 | 默认锁定路径使用。该文件位于 AgentSeek core 仓库，不在本仓库。 |

仅针对某个 catalog 原生模板的来源说明应写入该模板自己的 README，不应再
建立第二份 catalog 注册表。

## 许可证

Apache License 2.0，详见 [LICENSE](LICENSE)。
