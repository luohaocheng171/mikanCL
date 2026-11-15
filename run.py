"""顶层启动脚本：python run.py"""

from mc_launcher.main import main

if __name__ == "__main__":
    # Python 3.15+ 可选启用 PEP 810 原生惰性导入。
    # 默认关闭（不改变启动语义）；设置 MIKAN_LAZY_IMPORTS=all 时启用全量惰性导入。
    # 3.14 及以下自动跳过；源码不写 3.15 专有语法，打包 exe 不受影响。
    try:
        from mc_launcher.lazy import enable_lazy_imports

        enable_lazy_imports("normal")
    except Exception:  # noqa: BLE001 - 惰性导入是可选优化，失败不能阻止启动
        pass
    main()
