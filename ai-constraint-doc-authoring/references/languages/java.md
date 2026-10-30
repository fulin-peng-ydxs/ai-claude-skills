# Java 验证

## 识别

出现以下文件或结构时，将组件视为 Java 项目：`pom.xml`、`build.gradle`、`build.gradle.kts`、`settings.gradle`、`settings.gradle.kts`、`mvnw`、`gradlew`，或 `src/main` 下存在 Java/Kotlin 源码。

需要读取：

- Maven `pom.xml`：确认 Java 版本、插件、Spring Boot、模块和测试设置。
- Gradle 构建文件：确认 toolchain、插件、任务和 wrapper。
- `.java-version`、`.sdkmanrc`、Docker 文件、README 和启动脚本。

## 验证

优先使用 wrapper：

- Maven wrapper：`./mvnw`
- Gradle wrapper：`./gradlew`

只有没有 wrapper 且仓库文档允许时，才使用全局 `mvn` 或 `gradle`。

常见命令：

- 环境：`java -version`
- 构建工具：`./mvnw -version`、`mvn -version`、`./gradlew --version` 或 `gradle --version`
- 测试：`./mvnw test` 或 `./gradlew test`
- 构建：按项目惯例使用 `./mvnw package`、`./mvnw verify` 或 `./gradlew build`
- 本地启动：只有构建文件或文档确认后，才写 `./mvnw spring-boot:run`、`./gradlew bootRun`、生成 jar 命令或仓库脚本。

## 写入文档

记录：

- 要求的 JDK 版本和本次实际 `java -version`。
- Maven/Gradle wrapper 使用规则。
- 已通过的测试和构建命令。
- 服务 profile、端口、健康检查和停止命令，仅在验证通过后写入。

除非仓库确实同时支持 Maven 和 Gradle，否则不要在文档中混写两套命令。
