"""Streamlit entry point.

    streamlit run streamlit_app.py

The environment is prepared first: ``src.core`` reads its settings once, when it is imported.
"""

from src.ui.bootstrap import prepare_environment

prepare_environment()

from src.ui.app import main  # noqa: E402  (must follow prepare_environment)

main()
