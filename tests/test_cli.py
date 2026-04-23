from app import cli
from app.schemas import PromptResponse


def test_build_parser_accepts_one_shot_prompt():
    args = cli.build_parser().parse_args(
        [
            "Tell",
            "me",
            "about",
            "projects",
            "--resume-path",
            "resume.md",
            "--log-level",
            "DEBUG",
            "--no-log-color",
            "--show-trace",
        ]
    )

    assert " ".join(args.prompt) == "Tell me about projects"
    assert args.resume_path == "resume.md"
    assert args.log_level == "DEBUG"
    assert args.no_log_color is True
    assert args.show_trace is True


def test_main_runs_one_shot_prompt(monkeypatch, capsys):
    async def fake_run_once(prompt, subject, context, resume_path, docs_path, show_trace):
        response = PromptResponse(
            answer=f"answer: {prompt}",
            session_id=None,
            history=[],
            is_relevant=True,
            intent="projects",
            route="portfolio_query",
            retrieval_sources=["projects"],
            retrieval_reason="Project questions need project data.",
            retrieval_errors=[],
            rewritten_query=prompt,
            node_trace=["ingest_user_message", "generate_answer"],
        )
        cli._print_response(response, show_trace)
        return response

    monkeypatch.setattr(cli, "run_once", fake_run_once)

    exit_code = cli.main(["What", "projects?", "--subject", "Alex", "--show-trace"])

    output = capsys.readouterr().out
    assert exit_code == cli.EXIT_SUCCESS
    assert "answer: What projects?" in output
    assert "rewritten_query: What projects?" in output
    assert "sources: projects" in output
    assert "source_reason: Project questions need project data." in output
    assert "trace: ingest_user_message -> generate_answer" in output


def test_interactive_cli_exits_cleanly_on_eof(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(EOFError))

    exit_code = cli.main([])

    output = capsys.readouterr().out
    assert exit_code == cli.EXIT_SUCCESS
    assert "Portfolio assistant CLI." in output
    assert "Ending portfolio assistant session." in output


def test_interactive_cli_exits_cleanly_on_keyboard_interrupt(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(KeyboardInterrupt))

    exit_code = cli.main([])

    output = capsys.readouterr().out
    assert exit_code == cli.EXIT_SUCCESS
    assert "Portfolio assistant CLI." in output
    assert "Ending portfolio assistant session." in output
