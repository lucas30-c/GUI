"""测试替身（test doubles）——仅位于测试范围内。

Real-Provider-only（Owner 决策）：生产源码树（src/genui_api）不包含任何 Mock
Provider 或模板；生产链路只使用真实 Provider。本包内的替身仅供后端测试注入
（create_app 的 dependency_overrides / 直接传入 Pipeline），不出现在任何生产导入图。
"""

from tests.doubles.generation import MockGenerationProvider
from tests.doubles.refinement import MockProvider

__all__ = ["MockGenerationProvider", "MockProvider"]
