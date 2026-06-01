from __future__ import annotations

try:
    from omnilit_qt.app import run
except ImportError as exc:
    raise SystemExit(
        "OmniLit Qt/QML dependencies are missing. Activate the OmniLit Conda "
        "environment and run: conda env update -n OmniLit -f environment.yml --prune"
    ) from exc


if __name__ == "__main__":
    raise SystemExit(run())
# TODO:
'''
1文献翻译目录只收缩为一个文献翻译目录，输出的out文件夹重命名为一个以文献名为名的文件夹，



2实时翻译预览，在用户预览的时候，不能回滚到第一行



3文献翻译界面应该有显示当前文件目录下有什么文献待翻译，当前目录空请添加文献



4鼠标指到侧边栏文献下载或者文献翻译的区域时，如果当前有文献下载或者文献翻译，可以提示不再是文献下载或者文献翻译，而是当前执行的任务，比如正在根据什么关键词下载，正在翻译什么文献



3拓展栏的界面语言选项应该做成和下面界面外观和更新管理一样的拓展



4头像设置的上传头像和清除头像也应该是点击用户头像后，再同样的拓展逻辑



5头像状态也是一样，点击用户名旁边的状态后展开拓展，进行设置状态
'''
