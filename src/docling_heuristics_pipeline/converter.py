from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .final_document import build_final_document
from .filtered_document import build_filtered_document
from .llm_filtered_document import build_llm_filtered_document
from .logical_document import build_logical_document


def build_converter() -> Any:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False
    pipeline_options.do_table_structure = True

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options
            )
        }
    )


def validate_input_pdf(input_pdf: Path) -> None:
    if not input_pdf.exists():
        raise FileNotFoundError(f"No existe el archivo: {input_pdf}")

    if not input_pdf.is_file():
        raise ValueError(f"La ruta no es un archivo válido: {input_pdf}")

    if input_pdf.suffix.lower() != ".pdf":
        raise ValueError(f"El archivo no es un PDF: {input_pdf}")


def export_conversion_outputs(
    output_root_dir: Path,
    input_pdf: Path,
    json_clean: dict[str, Any],
    filtered_json: dict[str, Any],
    final_json: dict[str, Any],
) -> dict[str, Any]:
    output_dir = output_root_dir / input_pdf.stem
    json_path = output_dir / f"{input_pdf.stem}.json"
    filtered_json_path = output_dir / f"{input_pdf.stem}.filtered.json"
    final_json_path = output_dir / f"{input_pdf.stem}.final.json"

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(json_clean, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    filtered_json_path.write_text(
        json.dumps(filtered_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    final_json_path.write_text(
        json.dumps(final_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "output_dir": str(output_dir),
        "json_path": str(json_path),
        "filtered_json_path": str(filtered_json_path),
        "final_json_path": str(final_json_path),
        "json_clean": json_clean,
        "filtered_json": filtered_json,
        "final_json": final_json,
    }


def convert_pdf(
    input_pdf: str | Path,
    output_root_dir: str | Path,
    metadata_dir: str | Path | None = None,
    dotenv_path: str | Path | None = None,
) -> dict[str, Any]:
    input_pdf = Path(input_pdf).resolve()
    output_root_dir = Path(output_root_dir).resolve()
    resolved_metadata_dir = Path(metadata_dir).resolve() if metadata_dir is not None else None

    validate_input_pdf(input_pdf)
    output_root_dir.mkdir(parents=True, exist_ok=True)

    converter = build_converter()
    result = converter.convert(str(input_pdf))

    if not hasattr(result, "document") or result.document is None:
        raise RuntimeError("La conversión no devolvió un documento válido.")

    doc = result.document
    json_clean = doc.export_to_dict()
    logical_json = build_logical_document(json_clean)
    filtered_json = build_filtered_document(logical_json, metadata_dir=resolved_metadata_dir)
    llm_filtered_json, _raw_response = build_llm_filtered_document(
        filtered_json,
        dotenv_path=dotenv_path or ".env",
    )
    final_json = build_final_document(
        llm_filtered_json,
        metadata_dir=resolved_metadata_dir,
    )

    return export_conversion_outputs(
        output_root_dir=output_root_dir,
        input_pdf=input_pdf,
        json_clean=json_clean,
        filtered_json=filtered_json,
        final_json=final_json,
    )


def convert_pdf_for_pipeline(
    *,
    input_pdf: str | Path,
    output_root_dir: str | Path,
    metadata_dir: str | Path | None,
    dotenv_path: str | Path | None,
    document_id: str,
    doi: str,
    base_name: str,
) -> dict[str, Any]:
    result = convert_pdf(
        input_pdf=input_pdf,
        output_root_dir=output_root_dir,
        metadata_dir=metadata_dir,
        dotenv_path=dotenv_path,
    )

    return {
        "document_id": document_id,
        "doi": doi,
        "base_name": base_name,
        "output_dir": Path(result["output_dir"]),
        "json_path": Path(result["json_path"]),
        "filtered_json_path": Path(result["filtered_json_path"]),
        "final_json_path": Path(result["final_json_path"]),
    }


def print_single_result(input_pdf: Path, result: dict[str, Any]) -> None:
    print(f"OK: {input_pdf.name}")
    print(f"  output_dir: {result['output_dir']}")
    print(f"  json: {result['json_path']}")
    print(f"  filtered_json: {result['filtered_json_path']}")
    print(f"  final_json: {result['final_json_path']}")


def process_input(input_path: str | Path, output_dir: str | Path) -> None:
    input_path = Path(input_path).resolve()
    output_dir = Path(output_dir).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"No existe la ruta de input: {input_path}")

    if input_path.is_file():
        result = convert_pdf(input_path, output_dir)
        print_single_result(input_path, result)
        return

    if input_path.is_dir():
        pdfs = sorted(input_path.glob("*.pdf"))

        if not pdfs:
            print(f"No se encontraron PDFs en: {input_path}")
            return

        print(f"Se encontraron {len(pdfs)} PDF(s) en: {input_path}")

        ok_count = 0
        fail_count = 0

        for pdf in pdfs:
            try:
                result = convert_pdf(pdf, output_dir)
                ok_count += 1
                print_single_result(pdf, result)
            except Exception as e:
                fail_count += 1
                print(f"ERROR: {pdf.name} -> {e}")

        print("\nResumen")
        print(f"  exitosos: {ok_count}")
        print(f"  fallidos: {fail_count}")
        return

    raise ValueError("El input debe ser un archivo PDF o una carpeta con PDFs.")
