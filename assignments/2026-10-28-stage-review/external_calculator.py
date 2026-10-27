"""Independent HTTP tool process, loopback only; no eval, files, or network tools."""
import ast
import math
import operator
from flask import Flask, request, jsonify

app = Flask(__name__)
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.USub: operator.neg, ast.UAdd: operator.pos}

def calculate(expression):
    if not isinstance(expression, str) or not 1 <= len(expression) <= 120:
        raise ValueError('表达式须为 1–120 字符')
    tree = ast.parse(expression, mode='eval')
    if len(list(ast.walk(tree))) > 60:
        raise ValueError('表达式过于复杂')
    def visit(node):
        if isinstance(node, ast.Expression): return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float): return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            return OPS[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
            return OPS[type(node.op)](visit(node.operand))
        raise ValueError('只允许数字、括号和加减乘除')
    result = visit(tree)
    if not math.isfinite(result) or abs(result) > 1e15:
        raise ValueError('结果超出范围')
    return result

@app.post('/calculate')
def api():
    try:
        payload = request.get_json(silent=True) or {}
        expression = payload.get('expression')
        return jsonify(expression=expression, result=calculate(expression))
    except (ValueError, SyntaxError, TypeError, ArithmeticError, AttributeError):
        return jsonify(error='表达式无效'), 400

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8093, debug=False)
