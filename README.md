# 念响AI · 内容OS

面向个人 IP 与一人公司的开源内容 Skill。阿响是系统中的内容 Agent：和你一起判断素材、挑选题、写朋友圈、做口播，并在你授权后保存作品与个人内容知识。

**首发公共基线：v0.1.0-beta.9 · Beta。** 公共方法、提示词、管理脚本和测试使用 [MIT 许可证](LICENSE)开放。体验细节继续迭代；跨平台完整旅程与云端重启持久性尚未全部验收。

## 能做什么

- **聊素材、挖选题**：找到值得讲的判断，保留事实、来源与公开边界。
- **写朋友圈、做口播**：从素材共创、改稿、审稿到渠道转换。
- **按授权沉淀**：对接飞书个人内容知识库、作品和选题池，保存后回读。
- **管理公共更新**：管理脚本提供本地可信包验收、受控切换、回退与中断恢复。

不连接知识库也能用：提供素材、目标和限制，先完成本轮创作。私人长期知识、认证信息和运行配置留在公共 Skill 之外。

## 下载与安装

克隆本仓库，或在 GitHub 页面点击 **Code → Download ZIP** 下载完整仓库：

```sh
git clone https://github.com/KaenZhong/nianxiang-content-os.git
```

真正的 Skill 包位于仓库内的 **`nianxiang-content-os/` 子目录**。将该目录交给支持 Skill 的 Agent 导入，让安装 Agent 先读取其中的 `SKILL.md` 与 [安装说明](nianxiang-content-os/references/system/installation.md)。仓库根目录的管理文件与 `.git/` 不属于 Skill 安装内容；分发 Skill 副本时须同时保留根目录的 MIT 许可及版权声明。

**Codex 首次安装：** 将上述子目录放入你的 Codex Skill 目录，使其结构为 `~/.codex/skills/nianxiang-content-os/SKILL.md`，在新对话中调用 `$nianxiang-content-os` 或“阿响”。已有安装先按 [受控更新](nianxiang-content-os/references/maintenance/releases.md)检查版本与日志，不直接覆盖。

其他平台的接入与能力检查见 [三平台接入说明](nianxiang-content-os/docs/platform-setup.md)。导入后先确认私人目录位置和持久性；首次创建或接管须由你确认。不同平台的文件、原生选择卡和飞书工具能力以实际环境为准。

## 第一次使用

可以直接说：

> 阿响，先聊聊下面这段经历值得讲什么。

> 写朋友圈，把下面这份素材写成稿；不添加没有依据的经历和数字。

> 做口播，用这篇未发表的稿。

想建立长期知识库时，再说“阿响，帮我建立个人内容知识库”。完整用法见 [Skill 使用说明](nianxiang-content-os/README.md)和 [任务入口](nianxiang-content-os/SKILL.md)。

## 当前状态与已知限制

- 本次公开采用 **beta.9**，与维护者当前 Codex 安装的公共文件一致。仓库历史中的 beta.10 兼容试验不作为当前推荐安装版本。
- 本地合成资料及隔离目录下的 **160 项自动测试通过**。这些检查不等同于所有平台、真实账号和完整创作行为都已验收。
- 飞书读写需要相应工具和用户账号授权；当前包没有统一平台自动安装器。
- 跨平台完整使用旅程、云端重启后的私人目录持久性及部分体验收口细节仍待后续验证。
- `release_source=null`：管理脚本尚无自动下载更新源。GitHub 源码公开不改变该行为。
- beta.9 包内部分文档保留发行时“许可证与 GitHub 发布待落实”的历史描述。本次公开许可与仓库位置以本 README 和根目录 [LICENSE](LICENSE)为准，旧标签内容不改写。

## 本地检查

Python 3.9 及以上，无第三方 Python 依赖。从仓库根目录运行：

```sh
python3 -B nianxiang-content-os/scripts/check_public_release.py
python3 -B nianxiang-content-os/scripts/manage.py doctor --offline
python3 -B -m unittest discover -s nianxiang-content-os/tests -q
```

测试使用合成资料和临时私人目录。`doctor --offline`检查本地能力，不访问生产知识库；公共排除检查默认只检查路径，维护者的私人部署值比对另行执行。

## 贡献与反馈

欢迎通过 GitHub Issues 提交平台、版本、复现步骤、预期与实际结果。只提交脱敏信息，不附私人正文、访问 token、账号配置或安装回执。改进可提交 Pull Request；公共包版本维护见 [维护规则](AGENTS.md)。

本仓库只包含公共源与维护工具。公共改动在本仓库形成提交，已发行标签不改写；许可证覆盖本仓库内由项目提供的公共代码与文档，不包含用户私人知识和用户创作内容。

## 维护者说明

`tools/sync_codex.py`是本机受管安装检查入口，默认路径面向维护者的 Codex 环境，普通用户首次安装按上文操作。同步前公共源须提交并通过清单核验；已有安装的受控日志与恢复流程必须保留。

历史标签 beta.2 至 beta.5 来自可核验的发行快照导入，不是原始开发时间的重建；没有可核验首版完整包，因此不补造 beta.1 标签。后续版本按实际开发提交记录。

开发者：卡昂（KaenZhong） · 公众号：卡昂AI超能玩 · 使用反馈：kaenzhong@foxmail.com
