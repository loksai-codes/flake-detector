"""Offline tests for GroqAgent, AST calculator, and backoff logic."""

from typing import Any

from flake_detector.agents.groq_agent import GroqAgent, calculate_backoff_delay
from flake_detector.agents.tools import calculator, lookup_fact
from flake_detector.models import GraderSpec, Suite, Task
from flake_detector.runner import run_suite

# ================= Fake OpenAI Client Helpers (Zero Network) =================

class FakeFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: str) -> None:
        self.id = call_id
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(
        self,
        content: str | None = None,
        tool_calls: list[FakeToolCall] | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls


class FakeChoice:
    def __init__(self, message: FakeMessage) -> None:
        self.message = message


class FakeUsage:
    def __init__(self, prompt_tokens: int = 15, completion_tokens: int = 25) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class FakeResponse:
    def __init__(self, message: FakeMessage, usage: FakeUsage | None = None) -> None:
        self.choices = [FakeChoice(message)]
        self.usage = usage or FakeUsage()


class FakeCompletions:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.recorded_calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.recorded_calls.append(kwargs)
        if not self.responses:
            raise RuntimeError("FakeCompletions: No more scripted responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeChat:
    def __init__(self, completions: FakeCompletions) -> None:
        self.completions = completions


class FakeOpenAIClient:
    def __init__(self, responses: list[Any]) -> None:
        self.chat = FakeChat(FakeCompletions(responses))


# ================= Test Cases =================

def test_calculator_safe_evaluations() -> None:
    """Verify calculator handles standard arithmetic and edge cases correctly."""
    assert calculator("17 * 23") == "391"
    assert calculator("1000 / 8") == "125"
    assert calculator("2 ** 10") == "1024"
    assert calculator("(15 + 25) * 4") == "160"
    assert calculator("100 % 30") == "10"
    assert calculator("-42 + 2") == "-40"
    assert calculator("10 / 0") == "Error: Division by zero"
    assert "Empty" in calculator("")


def test_calculator_security_rejections() -> None:
    """Calculator must reject code execution, attribute lookups, names, and imports."""
    unsafe_inputs = [
        "__import__('os').system('echo pwned')",
        "open('/etc/passwd').read()",
        "import os",
        "x + 1",
        "eval('2 + 2')",
        "''.__class__.__mro__",
        "lambda x: x + 1",
        "2 ** 1000",  # Astronomical exponent attack
    ]
    for expr in unsafe_inputs:
        result = calculator(expr)
        msg = f"Expression '{expr}' was not rejected! Result: {result}"
        assert result.startswith("Error:"), msg


def test_lookup_fact() -> None:
    """lookup_fact returns verified facts for known keys and friendly errors otherwise."""
    assert lookup_fact("capital_of_france") == "Paris"
    assert lookup_fact("apollo_11_year") == "1969"
    assert "Guido van Rossum" in lookup_fact("python_creator")
    assert "Fact not found" in lookup_fact("unknown_nonexistent_key")


def test_backoff_delay_schedule() -> None:
    """Backoff delay follows 1s, 2s, 4s, 8s, 16s, capped at 30s with Retry-After override."""
    # Attempts 1 to 6 without jitter
    assert calculate_backoff_delay(1, jitter=False) == 1.0
    assert calculate_backoff_delay(2, jitter=False) == 2.0
    assert calculate_backoff_delay(3, jitter=False) == 4.0
    assert calculate_backoff_delay(4, jitter=False) == 8.0
    assert calculate_backoff_delay(5, jitter=False) == 16.0
    assert calculate_backoff_delay(6, jitter=False) == 30.0  # Capped at max_delay

    # Retry-After header override when larger than exponential delay
    assert calculate_backoff_delay(2, retry_after=12.0, jitter=False) == 12.0
    # Retry-After ignored if smaller than calculated delay
    assert calculate_backoff_delay(5, retry_after=5.0, jitter=False) == 16.0


def test_groq_agent_tool_loop_mocked() -> None:
    """Model executes a tool call to calculator, gets result, and produces final answer."""
    # Turn 1: Model requests calculator call
    msg1 = FakeMessage(
        content=None,
        tool_calls=[FakeToolCall("call_1", "calculator", '{"expression": "23 * 47"}')],
    )
    # Turn 2: Model returns answer after receiving tool response
    msg2 = FakeMessage(content="The product of 23 and 47 is 1081.")

    fake_client = FakeOpenAIClient([FakeResponse(msg1), FakeResponse(msg2)])
    agent = GroqAgent(api_key="mock_key", client=fake_client)

    task = Task(
        id="calc-task",
        prompt="Calculate 23 * 47",
        grader=GraderSpec(type="numeric", expected=1081),
    )

    out = agent.run(task, seed=42)
    assert out.answer == "The product of 23 and 47 is 1081."
    assert out.error is None
    assert out.steps == 2
    assert out.tokens_in > 0
    assert out.tokens_out > 0


def test_groq_agent_step_cap_mocked() -> None:
    """Agent returns max_steps error when exceeding the 6-step tool call limit."""
    # 6 consecutive tool calls without producing a final message
    infinite_tool_calls = [
        FakeResponse(
            FakeMessage(
                content=None,
                tool_calls=[FakeToolCall(f"call_{i}", "calculator", '{"expression": "1 + 1"}')],
            )
        )
        for i in range(6)
    ]

    fake_client = FakeOpenAIClient(infinite_tool_calls)
    agent = GroqAgent(api_key="mock_key", client=fake_client)

    task = Task(
        id="infinite-task",
        prompt="Infinite tool call loop",
        grader=GraderSpec(type="numeric", expected=2),
    )

    out = agent.run(task, seed=42)
    assert out.answer is None
    assert "Max steps exceeded" in (out.error or "")
    assert out.steps == 6


def test_api_key_never_serialized() -> None:
    """API key must never appear in agent config, output, or serialized RunResults."""
    secret_key = "gsk_test_secret_key_never_leak_98765"
    fake_client = FakeOpenAIClient([
        FakeResponse(FakeMessage(content="Simple answer."))
    ])

    agent = GroqAgent(api_key=secret_key, client=fake_client)
    assert secret_key not in str(agent.config)

    suite = Suite(
        name="secret-test-suite",
        tasks=[
            Task(
                id="t1",
                prompt="Say hello",
                grader=GraderSpec(type="contains", expected="answer"),
            )
        ],
    )

    results = run_suite(suite, agent, runs=1, seed=42)
    serialized = results.model_dump_json()

    assert secret_key not in serialized
    assert secret_key not in repr(results)
