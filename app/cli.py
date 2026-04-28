import argparse
import asyncio
from collections.abc import Sequence

from app.config import Settings, SettingsError, require_settings
from app.logging_config import configure_logging
from app.schemas import ConversationTurn, PromptRequest, PromptResponse
from app.services.prompt_runner import run_prompt


EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_KEYBOARD_INTERRUPT = 130
SESSION_END_MESSAGE = "\nEnding portfolio assistant session."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="portfolio-assistant",
        description="Run the LangGraph portfolio assistant from the terminal.",
    )
    parser.add_argument("prompt", nargs="*", help="Prompt to run once. Omit for interactive mode.")
    parser.add_argument(
        "--subject",
        help="Portfolio subject to answer about. Defaults to ASSISTANT_SUBJECT.",
    )
    parser.add_argument(
        "--context",
        help="Inline extra context for this run. Prefer --resume-path for profile/resume data.",
    )
    parser.add_argument(
        "--resume-path",
        help="Path to a local text/Markdown resume source for this run.",
    )
    parser.add_argument(
        "--docs-path",
        help="Path to a local text/Markdown docs source for this run. Defaults to DOCS_PATH.",
    )
    parser.add_argument(
        "--show-trace",
        action="store_true",
        help="Print the graph node trace after each answer.",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Console log level. Defaults to LOG_LEVEL.",
    )
    parser.add_argument(
        "--no-log-color",
        action="store_true",
        help="Disable ANSI colors in console logs.",
    )
    parser.add_argument(
        "--log-format",
        choices=["text", "json"],
        help="Console log format. Defaults to LOG_FORMAT.",
    )
    return parser


async def run_once(
    settings: Settings,
    prompt: str,
    subject: str | None,
    context: str | None,
    resume_path: str | None,
    docs_path: str | None,
    show_trace: bool,
) -> PromptResponse:
    request = PromptRequest(
        prompt=prompt,
        assistant_subject=subject,
        portfolio_context=context,
        resume_path=resume_path,
        docs_path=docs_path,
    )
    response = await run_prompt(request, settings)
    _print_response(response, show_trace)
    return response


async def run_interactive(
    settings: Settings,
    subject: str | None,
    context: str | None,
    resume_path: str | None,
    docs_path: str | None,
    show_trace: bool,
) -> None:
    print("Portfolio assistant CLI. Type 'exit' or 'quit' to stop.")
    history: list[ConversationTurn] = []

    while True:
        try:
            prompt = input("> ").strip()
        except EOFError:
            print(SESSION_END_MESSAGE)
            return

        if prompt.lower() in {"exit", "quit"}:
            print(SESSION_END_MESSAGE)
            return
        if not prompt:
            continue

        request = PromptRequest(
            prompt=prompt,
            history=history,
            assistant_subject=subject,
            portfolio_context=context,
            resume_path=resume_path,
            docs_path=docs_path,
        )
        response = await run_prompt(request, settings)
        _print_response(response, show_trace)
        history = response.history


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    prompt = " ".join(args.prompt).strip()
    try:
        settings = require_settings()
    except SettingsError as exc:
        parser.exit(EXIT_ERROR, f"error: {exc}\n")
    configure_logging(
        args.log_level or settings.log_level,
        use_color=settings.log_color and not args.no_log_color,
        log_format=args.log_format or settings.log_format,
        force=True,
    )

    try:
        if prompt:
            asyncio.run(
                run_once(
                    settings,
                    prompt,
                    args.subject,
                    args.context,
                    args.resume_path,
                    args.docs_path,
                    args.show_trace,
                )
            )
        else:
            asyncio.run(
                run_interactive(
                    settings,
                    args.subject,
                    args.context,
                    args.resume_path,
                    args.docs_path,
                    args.show_trace,
                )
            )
    except KeyboardInterrupt:
        print(SESSION_END_MESSAGE)
        return EXIT_SUCCESS if not prompt else EXIT_KEYBOARD_INTERRUPT
    except ValueError as exc:
        parser.exit(EXIT_ERROR, f"error: {exc}\n")
    except Exception as exc:
        parser.exit(EXIT_ERROR, f"error: prompt processing failed: {exc}\n")

    return EXIT_SUCCESS


def _print_response(response: PromptResponse, show_trace: bool) -> None:
    print(response.answer)
    if show_trace:
        if response.rewritten_query:
            print(f"\nrewritten_query: {response.rewritten_query}")
        if response.retrieval_sources:
            print(f"sources: {', '.join(response.retrieval_sources)}")
        if response.retrieval_reason:
            print(f"source_reason: {response.retrieval_reason}")
        if response.retrieval_errors:
            print(f"retrieval_errors: {' | '.join(response.retrieval_errors)}")
        print(f"\ntrace: {' -> '.join(response.node_trace)}")


if __name__ == "__main__":
    raise SystemExit(main())
