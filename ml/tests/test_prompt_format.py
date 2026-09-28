"""prompt_format.json: chat templates as string assembly (spec v1.1 §9.4, A-02).

Fake tokenizers stand in for Hugging Face ones, so these tests need neither Transformers nor
the network; the one test with a real tokenizer skips unless Transformers and a cached
tokenizer are available.
"""

import hashlib
import importlib.util
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tw_ml.datagen.records import TicketPayload
from tw_ml.export import prompt_format as pf
from tw_ml.export.prompt_format import (
    GOLDEN_COUNT,
    PromptFormat,
    PromptFormatError,
    derive_prompt_format,
    golden_user_messages,
    load_prompt_format,
    render_raw,
    runtime_prompt,
    verify_goldens,
    write_prompt_format,
)
from tw_ml.prompts import TriagePrompt, load_triage_prompt

SHA = "0123456789abcdef0123456789abcdef01234567"


@dataclass
class FakeChatML:
    """Qwen-style ChatML; an empty think block when thinking is off."""

    chat_template: str | None = "{# fake chatml #}"
    bos_token: str | None = None
    eos_token: str | None = "<|im_end|>"
    all_special_tokens: tuple[str, ...] = ("<|im_start|>", "<|im_end|>", "<|endoftext|>")
    calls: list[dict[str, object]] = field(default_factory=list)

    def get_added_vocab(self) -> dict[str, int]:
        return {"<think>": 1, "</think>": 2, "<|im_start|>": 3, "plainword": 4}

    def apply_chat_template(self, conversation: list[dict[str, str]], **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        text = "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in conversation)
        if kwargs.get("add_generation_prompt"):
            text += "<|im_start|>assistant\n"
            text += (
                "<think>\n\n</think>\n\n" if kwargs.get("enable_thinking") is False else "<think>\n"
            )
        return text


@dataclass
class FakeLlama:
    """Llama-3-style: BOS in the template, a dated system header, trimmed content."""

    chat_template: str | None = "{# fake llama #}"
    bos_token: str | None = "<|begin_of_text|>"
    eos_token: str | None = "<|eot_id|>"
    add_bos_token: bool = True
    all_special_tokens: tuple[str, ...] = (
        "<|begin_of_text|>",
        "<|eot_id|>",
        "<|start_header_id|>",
        "<|end_header_id|>",
    )

    def apply_chat_template(self, conversation: list[dict[str, str]], **kwargs: object) -> object:
        date = kwargs.get("date_string", "TODAY")
        out = "<|begin_of_text|>"
        for message in conversation:
            content, role = message["content"].strip(), message["role"]
            header = f"<|start_header_id|>{role}<|end_header_id|>\n\n"
            if role == "system":
                header += f"Cutting Knowledge Date: December 2023\nToday Date: {date}\n\n"
            out += f"{header}{content}<|eot_id|>"
        if kwargs.get("add_generation_prompt"):
            out += "<|start_header_id|>assistant<|end_header_id|>\n\n"
        return out


@dataclass
class FakeFolded:
    """Gemma-3-style: the system message is folded into the first user turn."""

    chat_template: str | None = "{# fake folded #}"
    bos_token: str | None = "<bos>"
    eos_token: str | None = "<eos>"
    all_special_tokens: tuple[str, ...] = ("<bos>", "<eos>", "<start_of_turn>", "<end_of_turn>")

    def apply_chat_template(self, conversation: list[dict[str, str]], **kwargs: object) -> object:
        system = next(m["content"] for m in conversation if m["role"] == "system")
        user = next(m["content"] for m in conversation if m["role"] == "user")
        out = f"<bos><start_of_turn>user\n{system}\n\n{user}<end_of_turn>\n"
        return out + ("<start_of_turn>model\n" if kwargs.get("add_generation_prompt") else "")


@pytest.fixture(scope="module")
def prompt() -> TriagePrompt:
    return load_triage_prompt()


def _hf(tokenizer: FakeChatML | FakeLlama | FakeFolded, system: str, user: str) -> object:
    conversation = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    return tokenizer.apply_chat_template(
        conversation,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
        date_string="26 Sep 2026",
    )


def test_chatml_format_is_derived_with_explicit_kwargs() -> None:
    tokenizer = FakeChatML()
    fmt = derive_prompt_format(tokenizer, base_model="Qwen/Qwen3.5-2B", base_revision=SHA)
    assert (fmt.bos, fmt.system_prefix, fmt.system_suffix) == (
        "",
        "<|im_start|>system\n",
        "<|im_end|>\n",
    )
    assert (fmt.user_prefix, fmt.user_suffix) == ("<|im_start|>user\n", "<|im_end|>\n")
    assert fmt.generation_prefix == "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    assert fmt.stop == ("<|im_end|>",)
    assert fmt.special_tokens == ("</think>", "<think>")  # bar tokens are caught by pattern
    assert fmt.runtime_adds_bos is False
    assert fmt.chat_template_sha256 == hashlib.sha256(b"{# fake chatml #}").hexdigest()
    assert fmt.template_kwargs == {
        "add_generation_prompt": True,
        "enable_thinking": False,
        "date_string": "26 Sep 2026",
    }
    assert all(c["enable_thinking"] is False and c["tokenize"] is False for c in tokenizer.calls)
    assert fmt.goldens == ()


def test_goldens_prove_string_assembly_on_real_prompts(
    prompt: TriagePrompt, make_ticket: Callable[..., TicketPayload]
) -> None:
    tokenizer = FakeChatML()
    users = golden_user_messages(prompt)
    assert len(users) == GOLDEN_COUNT == len(set(users))
    fmt = derive_prompt_format(
        tokenizer, base_model="m/x", base_revision=SHA, golden_prompt=prompt, golden_users=users
    )
    assert fmt.golden_prompt_version == "triage.v1"
    assert fmt.golden_system == prompt.system
    assert len(fmt.goldens) == GOLDEN_COUNT
    verify_goldens(fmt)
    user = prompt.render(make_ticket(), nonce="0123456789abcdef").user
    assert render_raw(fmt, prompt.system, user) == _hf(tokenizer, prompt.system, user)
    assert any("&lt;|im_end|>" in u for u in users)  # the goldens exercise neutralization


def test_llama_format_drops_the_bos_literal_for_the_runtime(prompt: TriagePrompt) -> None:
    tokenizer = FakeLlama()
    fmt = derive_prompt_format(
        tokenizer,
        base_model="meta-llama/Llama-3.2-3B-Instruct",
        base_revision=SHA,
        golden_prompt=prompt,
        golden_users=golden_user_messages(prompt, 3),
    )
    assert fmt.bos == "<|begin_of_text|>"
    assert fmt.runtime_adds_bos is True
    assert "Today Date: 26 Sep 2026" in fmt.system_prefix
    assert (fmt.system_suffix, fmt.stop) == ("<|eot_id|>", ("<|eot_id|>",))
    raw = render_raw(fmt, "S", "U")
    assert raw == _hf(tokenizer, "S", "U")
    assert runtime_prompt(fmt, "S", "U") == raw.removeprefix("<|begin_of_text|>")


def test_folded_system_template_still_assembles_exactly() -> None:
    tokenizer = FakeFolded()
    fmt = derive_prompt_format(tokenizer, base_model="google/gemma-x", base_revision=SHA)
    assert (fmt.bos, fmt.system_suffix, fmt.user_prefix) == ("<bos>", "\n\n", "")
    assert fmt.stop == ("<eos>", "<end_of_turn>")
    assert fmt.special_tokens == ("<bos>", "<end_of_turn>", "<eos>", "<start_of_turn>")
    assert render_raw(fmt, "S", "U") == _hf(tokenizer, "S", "U")


def test_a_template_that_rewrites_content_fails_the_goldens(prompt: TriagePrompt) -> None:
    with pytest.raises(
        PromptFormatError, match="differs from the chat template for goldens \\[1\\]"
    ):
        derive_prompt_format(
            FakeLlama(),
            base_model="m/x",
            base_revision=SHA,
            golden_prompt=prompt,
            golden_users=["kept as is", "  trimmed by the template  "],
        )


@dataclass
class Scripted:
    """A tokenizer whose two renderings (with / without generation prompt) are given."""

    with_generation: object
    without_generation: object
    chat_template: str | None = "{# scripted #}"
    bos_token: str | None = None
    eos_token: str | None = "<|im_end|>"

    def apply_chat_template(self, conversation: list[dict[str, str]], **kwargs: object) -> object:
        del conversation
        return (
            self.with_generation if kwargs.get("add_generation_prompt") else self.without_generation
        )


S, U = pf.SYSTEM_SENTINEL, pf.USER_SENTINEL


@pytest.mark.parametrize(
    ("tokenizer", "fragment"),
    [
        (FakeChatML(chat_template=None), "no chat template"),
        (Scripted([1, 2, 3], [1, 2]), "did not return text"),
        (Scripted(f"A{S}B{U}C!", f"X{S}B{U}C"), "not a pure suffix"),
        (Scripted(f"{S}{S}{U}G", f"{S}{S}{U}"), "drops or repeats message content"),
        (Scripted(f"{U}|{S}|G", f"{U}|{S}|"), "system message after the user message"),
        (Scripted(f"{S}|{U}|G", f"{S}|{U}|", eos_token=None), "cannot determine a stop token"),
    ],
)
def test_templates_string_assembly_cannot_express_are_refused(
    tokenizer: FakeChatML | Scripted, fragment: str
) -> None:
    with pytest.raises(PromptFormatError, match=fragment):
        derive_prompt_format(tokenizer, base_model="m/x", base_revision=SHA)


def test_goldens_need_their_prompt() -> None:
    with pytest.raises(PromptFormatError, match="golden_prompt"):
        derive_prompt_format(FakeChatML(), base_model="m/x", base_revision=SHA, golden_users=["u"])


def test_tampered_goldens_and_formats_are_detected(prompt: TriagePrompt, tmp_path: Path) -> None:
    fmt = derive_prompt_format(
        FakeChatML(),
        base_model="m/x",
        base_revision=SHA,
        golden_prompt=prompt,
        golden_users=golden_user_messages(prompt, 2),
    )
    tampered = fmt.model_copy(update={"generation_prefix": "<|im_start|>assistant\n"})
    with pytest.raises(PromptFormatError, match=r"goldens \[0, 1\]"):
        verify_goldens(tampered)
    path = write_prompt_format(tmp_path / "formats" / "x.json", fmt)
    assert load_prompt_format(path) == fmt
    raw = path.read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"}\n")


@pytest.mark.parametrize(
    ("content", "fragment"),
    [
        ("{not json", "is not a valid prompt_format.v1 file"),
        ('{"schema_version": "prompt_format.v2"}', "is not a valid prompt_format.v1 file"),
    ],
)
def test_invalid_format_files_are_refused(tmp_path: Path, content: str, fragment: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(PromptFormatError, match=fragment):
        load_prompt_format(path)
    with pytest.raises(PromptFormatError, match="not found"):
        load_prompt_format(tmp_path / "missing.json")


def test_cli_writes_a_verified_format(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[tuple[str, str, bool]] = []

    def fake_loader(model: str, revision: str, *, local_files_only: bool = False) -> FakeChatML:
        seen.append((model, revision, local_files_only))
        return FakeChatML()

    monkeypatch.setattr(pf, "load_tokenizer", fake_loader)
    out = tmp_path / "qwen.json"
    argv = ["--model", "Qwen/Qwen3.5-2B", "--revision", SHA, "--out", str(out), "--goldens", "4"]
    assert pf.main([*argv, "--local-files-only"]) == pf.EXIT_OK
    assert seen == [("Qwen/Qwen3.5-2B", SHA, True)]
    fmt = load_prompt_format(out)
    assert (fmt.base_model, fmt.base_revision, len(fmt.goldens)) == ("Qwen/Qwen3.5-2B", SHA, 4)
    verify_goldens(fmt)
    assert json.loads(capsys.readouterr().out)["goldens"] == 4


def test_cli_refuses_unpinned_revisions_and_reports_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = str(tmp_path / "x.json")
    assert pf.main(["--model", "m/x", "--revision", "main", "--out", out]) == pf.EXIT_USAGE
    assert "commit SHA" in capsys.readouterr().err

    def failing(model: str, revision: str, *, local_files_only: bool = False) -> PromptFormat:
        del model, revision, local_files_only
        raise PromptFormatError("transformers is not installed")

    monkeypatch.setattr(pf, "load_tokenizer", failing)
    assert pf.main(["--model", "m/x", "--revision", SHA, "--out", out]) == pf.EXIT_USAGE
    assert "transformers is not installed" in capsys.readouterr().err
    assert not Path(out).exists()


@pytest.mark.skipif(
    importlib.util.find_spec("transformers") is not None, reason="transformers is installed"
)
def test_load_tokenizer_explains_a_missing_transformers() -> None:
    with pytest.raises(PromptFormatError, match="transformers is not installed"):
        pf.load_tokenizer("Qwen/Qwen3-1.7B", SHA)


def test_real_tokenizer_round_trip_when_available(prompt: TriagePrompt) -> None:
    pytest.importorskip("transformers")
    try:  # pragma: no cover - needs transformers and a cached tokenizer
        tokenizer = pf.load_tokenizer("Qwen/Qwen3-1.7B", "main", local_files_only=True)
    except OSError:  # pragma: no cover
        pytest.skip("no cached Qwen/Qwen3-1.7B tokenizer")
    fmt = derive_prompt_format(  # pragma: no cover
        tokenizer,
        base_model="Qwen/Qwen3-1.7B",
        base_revision="main",
        golden_prompt=prompt,
        golden_users=golden_user_messages(prompt, 3),
    )
    assert fmt.generation_prefix.endswith("<think>\n\n</think>\n\n")  # pragma: no cover
