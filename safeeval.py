# -*- coding: utf-8 -*-
"""
Safe evaluate expression
Only support number evaluation and comparison evaluation

Example:
    >>> seval('1')
    1
    >>> seval('1 > 2')
    False
    >>> seval('1 >= 2')
    False
    >>> seval('1 < 2')
    True
    >>> seval('1 <= 2')
    True
    >>> seval('abc')
    Traceback (most recent call last):
        ...
    TypeError:
"""


import ast
import operator as op

# supported operators
operators = {ast.Gt: op.gt, ast.GtE: op.ge,
             ast.Lt: op.lt, ast.LtE: op.le,
             ast.Eq: op.eq}

def seval(expr):
    return seval_(ast.parse(expr, mode='eval').body)

def seval_(node):
    if isinstance(node, ast.Num):
        return node.n
    elif isinstance(node, ast.Compare):
        return operators[type(node.ops[0])](seval_(node.left), seval_(node.comparators[0]))
    else:
        raise TypeError(node, 'Not supported expression')
