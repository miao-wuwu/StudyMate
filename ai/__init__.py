# -*- coding: utf-8 -*-
"""StudyMate 的 AI 能力：本地大模型接入（阶段一）与文档问答（后续阶段）。

目录约定：
    config.py  配置（.env / 环境变量）
    llm.py     与模型打交道的唯一入口，provider 可切换
    router.py  FastAPI 路由，统一挂在 /ai 前缀下
"""
from .router import router  # noqa: F401  让 main.py 可以 from ai import router

__all__ = ["router"]
