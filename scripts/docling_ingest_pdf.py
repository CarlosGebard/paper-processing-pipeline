#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption


ROOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config_loader import get_config, get_pipeline_paths


def load_docling_defaults() -> tuple[Path, Path]:
    config = get_config()
    paths = get_pipeline_paths(config)
    return paths["docling_input_dir"], paths["docling_output_dir"]


def convert_pdf(input_pdf: Path, output_dir: Path, enable_ocr: bool) -> tuple[Path, Path]:
    if not input_pdf.exists() or not input_pdf.is_file():
        raise FileNotFoundError(f"No existe el PDF de entrada: {input_pdf}")

    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline_options = PdfPipelineOptions(do_ocr=enable_ocr)
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    result = converter.convert(str(input_pdf))

    json_output = output_dir / f"{input_pdf.stem}.json"
    md_output = output_dir / f"{input_pdf.stem}.md"

    with json_output.open("w", encoding="utf-8") as f:
        json.dump(result.document.export_to_dict(), f, ensure_ascii=False, indent=2)

    md_output.write_text(result.document.export_to_markdown(), encoding="utf-8")

    return json_output, md_output


def list_pdf_files(input_dir: Path, recursive: bool) -> list[Path]:
    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"No existe el directorio de entrada: {input_dir}")
    iterator = input_dir.rglob("*.pdf") if recursive else input_dir.glob("*.pdf")
    return sorted([p for p in iterator if p.is_file()])


def convert_pdf_batch(input_dir: Path, output_dir: Path, enable_ocr: bool, recursive: bool) -> list[tuple[Path, Path, Path]]:
    pdf_files = list_pdf_files(input_dir, recursive)
    if not pdf_files:
        raise RuntimeError(f"No se encontraron PDFs en: {input_dir}")

    results = []
    for pdf_file in pdf_files:
        json_file, md_file = convert_pdf(pdf_file, output_dir, enable_ocr)
        results.append((pdf_file, json_file, md_file))
    return results


def main() -> None:
    default_input_path, default_output_dir = load_docling_defaults()

    parser = argparse.ArgumentParser(
        description="Ingesta PDFs con Docling y genera salida JSON + Markdown"
    )
    parser.add_argument(
        "input_path",
        type=Path,
        nargs="?",
        default=default_input_path,
        help=(
            "Ruta a archivo PDF o carpeta con PDFs "
            f"(default desde config.yaml: {default_input_path})"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help=f"Directorio de salida (default desde config.yaml: {default_output_dir})",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Busca PDFs recursivamente si input_path es carpeta",
    )
    parser.add_argument(
        "--enable-ocr",
        action="store_true",
        help="Activa OCR (requiere descargar modelos en el primer uso)",
    )
    args = parser.parse_args()

    input_path = args.input_path if args.input_path.is_absolute() else (PROJECT_ROOT / args.input_path)
    output_dir = (
        args.output_dir if args.output_dir.is_absolute() else (PROJECT_ROOT / args.output_dir)
    )

    if input_path.is_file():
        json_file, md_file = convert_pdf(input_path, output_dir, args.enable_ocr)
        print("Conversion completada")
        print(f"PDF: {input_path}")
        print(f"JSON: {json_file}")
        print(f"Markdown: {md_file}")
        return

    if input_path.is_dir():
        batch_results = convert_pdf_batch(input_path, output_dir, args.enable_ocr, args.recursive)
        print("Conversion batch completada")
        print(f"Directorio entrada: {input_path}")
        print(f"Directorio salida: {output_dir}")
        print(f"PDFs procesados: {len(batch_results)}")
        for pdf_file, json_file, md_file in batch_results:
            print(f"- {pdf_file.name}")
            print(f"  JSON: {json_file}")
            print(f"  Markdown: {md_file}")
        return

    raise FileNotFoundError(f"La ruta de entrada no existe: {input_path}")


if __name__ == "__main__":
    main()
