# Vue / Node 验证

## 识别

当 `package.json` 包含 `vue`、`@vitejs/plugin-vue`、`vue-router`、`pinia`、`nuxt`，存在 Vite Vue 配置，或 `src/` 下存在 Vue 单文件组件时，将组件视为 Vue 项目。

需要读取：

- `package.json` 的 scripts、dependencies、devDependencies。
- 锁文件以确认包管理器：`package-lock.json`、`npm-shrinkwrap.json`、`pnpm-lock.yaml`、`yarn.lock`、`bun.lockb`。
- `vite.config.*`、`nuxt.config.*`、`.nvmrc`、`.node-version`、`volta`、`engines`、README 和启动脚本。

## 验证

使用锁文件对应的包管理器。不要因为本机装了其他包管理器就切换。

常见命令：

- 环境：`node --version`
- 包管理器：`npm --version`、`pnpm --version`、`yarn --version` 或 `bun --version`
- 依赖：`npm ci`、`pnpm install --frozen-lockfile`、`yarn install --frozen-lockfile`，或仓库明确写出的安装命令。若安装会重写锁文件或访问私有源，先询问用户。
- 测试：`test`、`test:unit` 或仓库文档指定的测试脚本。
- 构建：`build` 脚本，通常是 `npm run build` 或等价命令。
- 本地启动：优先使用根目录封装脚本；否则用 `dev` 脚本，并验证端口和清理方式。
- 预览：只有文档会单独推荐生产预览时才验证。

## 技术栈特有记录

落地前按 [输出契约](../output-contract.md#内容选择与表达) 区分长期规则与本次验证汇报，命令必须通过 [验证门禁](../verification-gate.md)。Vue / Node 项目补充 `.nvmrc`、`.node-version`、`engines`、`volta` 或 README 中的 Node 要求、包管理器与锁文件策略，以及经验证的开发服务器端口和代理行为。

`package.json` 中存在脚本只是候选命令证据，不代表已验证可用。
