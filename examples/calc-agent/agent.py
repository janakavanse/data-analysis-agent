"""A tiny Gemini ReAct calculator agent: ask a math question in English, it calls a safe `calculator`
tool and returns the number. Lean by design — a hand-rolled tool-calling loop, no agent framework."""
import ast
import operator
import os
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# --- safe calculator tool: AST-validated arithmetic only (numbers, + - * / ** %, parens) ----------
# No names, calls, or attribute access reach eval — the lean re-homing of v3's action-safety rule.
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError(f"unsupported expression: {ast.dump(node)}")


def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression such as '17 * 23 + 5'. Returns the result as a string."""
    result = _eval(ast.parse(expression, mode="eval"))
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return str(result)


# --- the agent: a hand-rolled tool-calling loop ---------------------------------------------------
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_TOOL = types.Tool(function_declarations=[types.FunctionDeclaration(
    name="calculator",
    description="Evaluate a basic arithmetic expression like '17 * 23 + 5'.",
    parameters=types.Schema(
        type="OBJECT",
        properties={"expression": types.Schema(type="STRING")},
        required=["expression"],
    ),
)])


def ask(question: str, *, client=None, max_steps: int = 5) -> str:
    client = client or genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    config = types.GenerateContentConfig(tools=[_TOOL])
    contents = [types.Content(role="user", parts=[types.Part(text=question)])]
    for _ in range(max_steps):
        resp = client.models.generate_content(model=MODEL, contents=contents, config=config)
        content = resp.candidates[0].content
        contents.append(content)
        calls = [p.function_call for p in (content.parts or []) if p.function_call]
        if not calls:
            return (resp.text or "").strip()
        for fc in calls:
            try:
                out = calculator(**(fc.args or {}))
            except Exception as e:                  # feed the error back so the model can react
                out = f"error: {e}"
            contents.append(types.Content(role="user", parts=[
                types.Part.from_function_response(name=fc.name, response={"result": out})
            ]))
    return "(ran out of steps)"


if __name__ == "__main__":
    print(ask(" ".join(sys.argv[1:]) or "what is 17 * 23 plus 5?"))
