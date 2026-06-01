# OmniLit macOS 打包说明

macOS 使用 Qt/QML 主入口：

```text
omnilit_qt_app.py
```

## 本地调试

```bash
conda env update -n OmniLit -f environment.yml --prune
conda activate OmniLit
python omnilit_qt_app.py
```

运行数据保存在源码根目录；打包版保存在 `OmniLit.app` 同级目录：

```text
OmniLit.app 同级目录
```

包括账号库、下载数据、翻译输入输出、可写术语表、加密 Key 和更新临时文件。可使用 `OMNILIT_DATA_DIR` 覆盖默认位置。

Qt 界面包含短时页面过渡、弹窗动画和任务忙碌反馈；动画不会改变下载、翻译或更新任务的执行顺序。

部署默认 Key 的生成和解锁位于翻译页默认收起的“部署 Key 高级选项”；构建脚本仍可使用 `--refresh-key` 或 `--encrypt-default-key` 预置部署 Key。

## 打包

先激活 `OmniLit` Conda 环境。构建脚本只使用 `$CONDA_PREFIX/bin/python`，不会自动安装依赖或回退到系统 Python。

```bash
conda activate OmniLit
chmod +x build_omnilit_macos.sh
./build_omnilit_macos.sh --skip-key
```

输出：

```text
dist/OmniLit.app
release/macos/OmniLit-macOS-版本号.zip
release/macos/OmniLit-macOS-版本号.zip.sha256
```

可选参数：

```bash
./build_omnilit_macos.sh --refresh-key
./build_omnilit_macos.sh --encrypt-default-key
OMNILIT_MAC_ARCH=universal2 ./build_omnilit_macos.sh
```

## 更新

macOS 客户端始终使用内置官方更新清单，先通过内置 Ed25519 公钥校验清单签名，再下载并校验更新文件 SHA-256。客户端不会覆盖正在运行的 `.app`；用户确认应用更新后，程序会打开下载目录并提示手动替换应用。

## GitHub Actions

仓库中的 `.github/workflows/build-macos.yml` 会在手动触发或推送 `v*` 标签时构建 artifact。CI 默认使用 `--skip-key`，不会把部署 Key 放入发布包。

发布给其他用户前，建议使用 Apple Developer 证书签名并完成 notarization。
