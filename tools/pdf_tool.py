from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict

from fpdf import FPDF


class _ReportPDF(FPDF):
    """
    Internal PDF class with header/footer for the AI report.
    """

    def __init__(self, *args: Any, header_title: str = "AI Research Report", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.header_title = header_title

    def header(self) -> None:  # type: ignore[override]
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, self.header_title, border=0, ln=1, align="C")
        self.ln(5)

    def footer(self) -> None:  # type: ignore[override]
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cell(0, 10, f"Generated: {timestamp}", 0, 0, "C")


class PDFReportTool:
    """
    Utility for generating professional PDF reports from agent outputs.

    Notes on UTF-8 / Turkish character support:
    - Core fonts (like Helvetica) in fpdf2 are not fully Unicode-aware.
    - To properly render Turkish characters, set the environment variable
      AGENTFLOW_PDF_FONT_PATH to a valid TTF font file (e.g. DejaVuSans).
    """

    ENV_FONT_PATH = "AGENTFLOW_PDF_FONT_PATH"

    def __init__(self) -> None:
        self.font_path = os.getenv(self.ENV_FONT_PATH)

    def _configure_font(self, pdf: FPDF) -> str:
        """
        Configure a Unicode-capable font if available, otherwise fall back.
        Returns the font family name to use.
        """
        if self.font_path and os.path.exists(self.font_path):
            # Register a TrueType font that supports UTF-8 (e.g. Turkish characters).
            pdf.add_font("AgentFlowUnicode", "", self.font_path, uni=True)
            return "AgentFlowUnicode"

        # Fallback: standard core font (limited Unicode support)
        return "Helvetica"

    def generate_report(self, title: str, content: str, filename: str) -> str:
        """
        Create a PDF report file.

        :param title: Title of the report content section.
        :param content: Main body text of the report.
        :param filename: Output PDF filename (path relative to current working dir or absolute).
        :return: The path to the generated PDF file.
        """
        pdf = _ReportPDF(format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        font_family = self._configure_font(pdf)

        # Document title
        pdf.set_font(font_family, "B", 16)
        pdf.cell(0, 10, title, ln=1)
        pdf.ln(4)

        # Body text
        pdf.set_font(font_family, "", 12)
        pdf.multi_cell(0, 8, content)

        # Ensure directory exists for the filename if needed
        output_path = os.path.abspath(filename)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        pdf.output(output_path)

        return output_path

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Return the tool schema in OpenAI/Ollama function-calling format.
        """
        return {
            "name": "generate_pdf_report",
            "description": (
                "Generate a professional AI research PDF report with a header, body text, and "
                "footer containing a timestamp. Use this to create human-readable summaries "
                "of your analysis or research."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title of the report content section (shown inside the PDF).",
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "Main body of the report. Can include multiple paragraphs and should "
                            "be plain text. Prefer concise but complete explanations."
                        ),
                    },
                    "filename": {
                        "type": "string",
                        "description": (
                            "Output PDF filename (e.g., 'reports/analysis.pdf'). Relative paths "
                            "are resolved from the application working directory."
                        ),
                    },
                },
                "required": ["title", "content", "filename"],
            },
        }


