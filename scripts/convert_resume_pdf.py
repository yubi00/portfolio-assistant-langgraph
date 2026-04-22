import argparse
from pathlib import Path

from pypdf import PdfReader


def convert_pdf_to_markdown(input_path: Path, output_path: Path) -> None:
    reader = PdfReader(str(input_path))
    page_texts = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        cleaned_text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if cleaned_text:
            page_texts.append(f"## Page {index}\n\n{cleaned_text}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("# Resume\n\n" + "\n\n".join(page_texts).strip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a resume PDF into a Markdown text source.")
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("output_md", type=Path)
    args = parser.parse_args()

    convert_pdf_to_markdown(args.input_pdf, args.output_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

