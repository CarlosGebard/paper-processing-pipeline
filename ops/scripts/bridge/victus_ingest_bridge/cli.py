import argparse
import json
from pathlib import Path
from typing import Any

from .bridge import VictusBridge
from .config import load_config


def _json_arg(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("JSON value must be an object")
    return parsed


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def cmd_ingest_pdf(args: argparse.Namespace) -> None:
    bridge = VictusBridge(load_config())
    print_json(bridge.ingest_pdf(args.path, doi=args.doi))


def cmd_mark_artifact_done(args: argparse.Namespace) -> None:
    bridge = VictusBridge(load_config())
    print_json(
        bridge.mark_artifact_done(
            args.paper_id,
            artifact_kind=args.artifact_kind,
            artifact_key=args.artifact_key,
            metadata=args.metadata_json,
        )
    )


def cmd_publish_event(args: argparse.Namespace) -> None:
    bridge = VictusBridge(load_config())
    print_json(bridge.publish_event(args.event_type, args.paper_id, args.payload_json))


def cmd_stage_start(args: argparse.Namespace) -> None:
    bridge = VictusBridge(load_config())
    print_json(bridge.mark_stage_started(args.paper_id, args.stage, args.worker_id))


def cmd_stage_done(args: argparse.Namespace) -> None:
    bridge = VictusBridge(load_config())
    print_json(bridge.mark_stage_done(args.paper_id, args.stage, args.metadata_json))


def cmd_publish_error(args: argparse.Namespace) -> None:
    bridge = VictusBridge(load_config())
    print_json(
        bridge.publish_error(
            service=args.service,
            error_type=args.error_type,
            message=args.message,
            severity=args.severity,
            paper_id=args.paper_id,
            stacktrace=args.stacktrace,
        )
    )


def cmd_status(args: argparse.Namespace) -> None:
    bridge = VictusBridge(load_config())
    print_json(bridge.status(args.paper_id))


def configure_parser(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="bridge_command", required=True)

    ingest_pdf = sub.add_parser("ingest-pdf", help="Register and upload source PDF")
    ingest_pdf.add_argument("path", type=Path)
    ingest_pdf.add_argument("--doi")
    ingest_pdf.set_defaults(handler=cmd_ingest_pdf)

    artifact = sub.add_parser("mark-artifact-done", help="Publish generic artifact completion")
    artifact.add_argument("paper_id")
    artifact.add_argument("--artifact-kind", required=True)
    artifact.add_argument("--artifact-key", required=True)
    artifact.add_argument("--metadata-json", type=_json_arg, default=None)
    artifact.set_defaults(handler=cmd_mark_artifact_done)

    event = sub.add_parser("publish-event", help="Publish generic event")
    event.add_argument("event_type")
    event.add_argument("--paper-id")
    event.add_argument("--payload-json", type=_json_arg, default=None)
    event.set_defaults(handler=cmd_publish_event)

    stage_start = sub.add_parser("stage-start", help="Mark generic stage started")
    stage_start.add_argument("paper_id")
    stage_start.add_argument("--stage", required=True)
    stage_start.add_argument("--worker-id")
    stage_start.set_defaults(handler=cmd_stage_start)

    stage_done = sub.add_parser("stage-done", help="Mark generic stage done")
    stage_done.add_argument("paper_id")
    stage_done.add_argument("--stage", required=True)
    stage_done.add_argument("--metadata-json", type=_json_arg, default=None)
    stage_done.set_defaults(handler=cmd_stage_done)

    error = sub.add_parser("publish-error", help="Publish error event")
    error.add_argument("--id", dest="paper_id")
    error.add_argument("--service", required=True)
    error.add_argument("--error-type", required=True)
    error.add_argument("--message", required=True)
    error.add_argument("--severity", choices=["low", "warning", "critical"], required=True)
    error.add_argument("--stacktrace")
    error.set_defaults(handler=cmd_publish_error)

    status = sub.add_parser("status", help="Read paper status")
    status.add_argument("paper_id")
    status.set_defaults(handler=cmd_status)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Victus communication bridge CLI")
    configure_parser(parser)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
