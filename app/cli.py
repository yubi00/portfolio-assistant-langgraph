import argparse
import asyncio
from collections.abc import Sequence

from pydantic import ValidationError

from app.config import get_settings
from app.schemas import ConversationTurn, PromptRequest, PromptResponse
from app.services.prompt_runner import run_prompt


EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_KEYBOARD_INTERRUPT = 130


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
        help="Inline portfolio context for this run. Defaults to PORTFOLIO_CONTEXT.",
    )
    parser.add_argument(
        "--show-trace",
        action="store_true",
        help="Print the graph node trace after each answer.",
    )
    return parser


async def run_once(prompt: str, subject: str | None, context: str | None, show_trace: bool) -> PromptResponse:
    request = PromptRequest(prompt=prompt, assistant_subject=subject, portfolio_context=context)
    response = await run_prompt(request, get_settings())
    _print_response(response, show_trace)
    return response


async def run_interactive(subject: str | None, context: str | None, show_trace: bool) -> None:
    print("Portfolio assistant CLI. Type 'exit' or 'quit' to stop.")
    history: list[ConversationTurn] = []

    while True:
        prompt = input("> ").strip()
        if prompt.lower() in {"exit", "quit"}:
            return
        if not prompt:
            continue

        request = PromptRequest(
            prompt=prompt,
            history=history,
            assistant_subject=subject,
            portfolio_context=context,
        )
        response = await run_prompt(request, get_settings())
        _print_response(response, show_trace)
        history.append(ConversationTurn(user=prompt, assistant=response.answer))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    prompt = " ".join(args.prompt).strip()

    try:
        if prompt:
            asyncio.run(run_once(prompt, args.subject, args.context, args.show_trace))
        else:
            asyncio.run(run_interactive(args.subject, args.context, args.show_trace))
    except KeyboardInterrupt:
        return EXIT_KEYBOARD_INTERRUPT
    except (ValidationError, ValueError) as exc:
        parser.exit(EXIT_ERROR, f"error: {exc}\n")
    except Exception as exc:
        parser.exit(EXIT_ERROR, f"error: prompt processing failed: {exc}\n")

    return EXIT_SUCCESS


def _print_response(response: PromptResponse, show_trace: bool) -> None:
    print(response.answer)
    if show_trace:
        if response.retrieval_sources:
            print(f"\nsources: {', '.join(response.retrieval_sources)}")
        if response.retrieval_reason:
            print(f"source_reason: {response.retrieval_reason}")
        print(f"\ntrace: {' -> '.join(response.node_trace)}")


if __name__ == "__main__":
    raise SystemExit(main())
