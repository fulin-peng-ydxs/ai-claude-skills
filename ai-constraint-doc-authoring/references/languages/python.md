# Python 验证

## 识别

出现以下文件或结构时，将组件视为 Python 项目：`pyproject.toml`、`requirements.txt`、`setup.py`、`setup.cfg`、`tox.ini`、`pytest.ini`、带 `__init__.py` 的包目录、`manage.py`、`app.py`、`main.py`、`backend/cli.py`。

需要读取：

- `pyproject.toml`：确认 `requires-python`、构建后端、pytest、ruff、mypy 和依赖。
- `requirements*.txt`：确认依赖版本下限。
- `README.md`、启动脚本、Docker 文件或进程配置：确认服务生命周期。
- 测试配置：确认测试路径和命令范围。

## 验证

优先使用仓库明确指定的 Python 命令；未指定时再使用 `python`。

常见命令：

- 环境：`python --version`
- 包工具：`python -m pip --version`
- 依赖：依赖已安装时使用 `python -m pip check`；只有仓库允许且必要时才执行安装。
- 测试：`python -m pytest -q` 或配置中明确的测试路径。
- Lint：仅当 Ruff 已配置或声明依赖时执行 `python -m ruff check .`。
- 构建：仅当项目声明可打包且 `build` 可用或已声明时执行 `python -m build`。
- 本地启动：优先使用仓库脚本；否则只有从代码确认入口后，才使用 `python -m <package>.cli serve`、`uvicorn module:app`、`fastapi dev`、`python manage.py runserver` 等框架命令。

## 写入文档

记录：

- `pyproject.toml` 中的 Python 要求范围，以及本次实际执行得到的本地版本。
- 已通过的测试命令和测试范围。
- 构建命令仅在通过后写入。
- 服务启动、状态、停止和健康检查仅在验证通过后写入。
- 仅当配置或文档能证明项目依赖时，才写 PostgreSQL、Redis、队列、对象存储或本地数据库等外部服务。

不要根据目录名猜框架命令；必须从代码、脚本或文档确认入口。
