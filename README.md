# OmniLit Qt/QML 桌面应用

OmniLit 是面向科研文献处理的桌面工具，整合本地账号、多来源文献下载、文献翻译、加密 API Key 和远程更新。

桌面界面已迁移到 PySide6 + QML。常规入口只有：

```text
omnilit_qt_app.py
```

## 功能

- **账号**：启动时登录或注册；可选择使用 Windows DPAPI 加密记住密码。下次启动自动填充，但不会自动登录。
- **文献下载**：按需检索 OpenAlex、Europe PMC 和 arXiv，筛选开放获取记录、下载 PDF、保存元数据、断点续跑和高级抓取参数。
- **文献翻译**：模型档案、自定义 OpenAI 兼容接口、术语表组合、缓存、实时译文预览、版式测试、进度和日志。
- **Key**：翻译页可按需展开“部署 Key 高级选项”；部署默认 Key 和用户自行记住的 Key 均使用 PBKDF2 + Fernet 加密保存。
- **界面**：支持中英文切换；下载页的起止日期支持手输和日历选择；学术外观系统支持主题预设、阅读舒适度、背景和实时预览。
- **更新**：登录后静默检查一次；Windows 打包版支持自动替换，macOS 下载后提示手动安装。

## 目录结构

```text
OmniLit/
  .github/workflows/            GitHub Actions 构建配置
  assets/                       应用图标和发布资源
  Download/
    literature_download_core.py 多来源文献检索和下载核心
    pdfs/                       已下载文献 PDF
    metadata_battery.jsonl      文献元数据
    crawl_state.json            下载断点状态
    gui_settings.json           下载页设置
  Translate/
    literature_translate_core.py 文献翻译核心
    glossary/                   可写术语表
    pdf/                        待翻译 PDF
    out/                        翻译输出
    APIKey.enc                  加密部署 Key
  Update/
    update_core.py              更新核心
  omnilit_qt/
    app.py                      Qt 应用装配
    controllers.py              页面控制器
    appearance.py               学术主题预设和外观选项
    paths.py                    资源和运行数据路径
    services.py                 动态模块加载和服务
    support.py                  通用辅助函数
    date_utils.py               日期处理
    i18n.py                     中英文文案
    secrets.py                  本地密钥处理
  ui/
    qml/                        QML 页面、主题和通用组件
    avatar-*.jpg                用户头像
  tests/
    test_qt_migration.py        Qt/QML 自动化测试
    smoke_update_apply.py       更新替换冒烟测试
  omnilit_qt_app.py             Qt/QML 启动入口
  encrypt_default_key.py        默认 Key 命令行生成器
  sync_release_metadata.py      发布版本和哈希同步工具
  build_omnilit_exe.bat         Windows 单文件构建脚本
  build_omnilit_macos.sh        macOS 构建脚本
  environment.yml               Conda 依赖声明
  update_manifest.json          更新清单
  version_info.txt              Windows 版本资源
  OmniLit.exe                   Windows 发布文件
  accounts.sqlite3              本地账号库
  .omnilit-data-migrated-v2     运行数据迁移标记
```

`.git/` 是版本库元数据。`.idea/`、`__pycache__/`、`build/`、`dist/`、`smoke_exe/`、QML 预览图和空闲时的 `updates/` 都属于可删除、可重建内容，已通过 `.gitignore` 排除。`updates/` 会在应用需要下载更新时自动创建。

打包资源是只读的。账号库、下载记录、PDF、翻译输出、Key、可写术语表和更新临时文件保存在程序目录：

```text
源码运行: 项目根目录
Windows: OmniLit.exe 同级目录
macOS:   OmniLit.app 同级目录
```

首次启动新版 Qt 时，应用会从旧 `%LOCALAPPDATA%\magicfoic\OmniLit` 等目录补齐已有运行数据。只复制目标目录中不存在的文件，不删除旧数据，也不覆盖程序目录中的内容。需要隔离测试时可设置 `OMNILIT_DATA_DIR` 覆盖数据目录。

`Translate/glossary` 是可写术语表目录。应用启动时补齐内置术语表，并动态扫描用户新增的 CSV、TSV、TXT、JSON 和 Markdown 文件。

Qt 界面使用克制的短过渡动画：按钮按压、页面切换、日期和确认弹窗、任务忙碌态以及高级选项展开都会提供即时反馈，不改变后台任务行为。

## 学术外观系统

账号抽屉中的“界面外观”支持动态切换，无需重启。设置保存在本地账号库的 `appearance/...` 键中，并兼容旧版主题与强调色配置。

内置预设：

```text
Scholar Light
Manuscript Sepia
Library Dark
Journal Blue
arXiv Minimal
Nature Green
```

可调项目包括强调色和自定义颜色、从背景图片提取主色、字体大小、界面密度、圆角、PDF 阅读背景、翻译区行距、背景模式、图片透明度、模糊、高对比度、减少动画，以及自动夜间开始和结束时间。外观面板提供论文卡片、DOI / arXiv 标签、下载进度和双语段落实时预览。

## 环境

项目使用本机 Conda 环境，不依赖系统 Python 或项目内 `.venv`。当前 Windows 开发机已确认环境路径为：

```text
D:\Tool\anaconda3\envs\OmniLit
```

初始化或更新环境：

```bat
conda env update -n OmniLit -f environment.yml --prune
conda activate OmniLit
python omnilit_qt_app.py
```

确认构建脚本定位到本地 Conda 环境：

```bat
build_omnilit_exe.bat --check-env
```

## 运行与验证

```bat
conda run -n OmniLit python -m unittest discover -s tests -v
conda run -n OmniLit python -m compileall -q omnilit_qt_app.py omnilit_qt Download Translate Update
```

## 默认 API Key

翻译页中默认收起的“部署 Key 高级选项”可以复用翻译表单里的 API Key 输入，生成部署用的：

```text
Translate/APIKey.enc
```

保存成功后，该 Key 会立即载入当前会话。部署 Key 高级区也可解锁已有文件，并显示文件状态、路径和当前解锁来源。

发布前也可以使用纯命令行工具：

```bat
conda run -n OmniLit python encrypt_default_key.py --output Translate\APIKey.enc
```

翻译页中用户自行输入的 Key 默认只在当前会话使用。用户主动选择“加密记住”后，应用会保存：

```text
Translate/UserAPIKey.enc
```

## Windows 打包

先激活 `OmniLit` Conda 环境。构建脚本只使用 `%CONDA_PREFIX%\python.exe`，不会自动安装依赖或回退到系统 Python。

```bat
conda activate OmniLit
conda env update -n OmniLit -f environment.yml --prune
build_omnilit_exe.bat
build_omnilit_exe.bat --skip-key
build_omnilit_exe.bat --refresh-key
build_omnilit_exe.bat --encrypt-default-key
build_omnilit_exe.bat --check-env
```

`build_omnilit_exe.bat` 会优先使用已激活的 `OmniLit` 环境；未激活时也会通过 Conda 自动定位该环境。

构建脚本使用 `omnilit_qt_app.py` 生成单文件 `OmniLit.exe`，并根据 `update_manifest.json` 同步版本信息和 SHA-256。

## 远程更新

客户端始终使用内置官方更新清单，不读取或修改历史数据库中的自定义地址：

```text
https://originchaos.top/omnilit/update_manifest.json
```

客户端每次检查都会绕过缓存读取最新清单，并比较远程版本和服务器发布文件 SHA-256。版本升高，或同版本 SHA-256 发生变化，都会触发更新。下载请求会携带目标 SHA-256 以隔离旧缓存，下载完成、替换前和替换后都会再次校验摘要。远程清单缺少合法 SHA-256 时拒绝更新。Windows 打包版可自动替换并重启；其他平台打开下载位置，由用户手动安装。

macOS 打包说明见 [README_macOS.md](README_macOS.md)。

Copyright (c) 2026 magicfoic. All rights reserved.
