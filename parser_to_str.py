from collections import namedtuple
import sympy

from numpy import sin, cos, tan, exp, log, sqrt, pi
from lark import Lark, Transformer

with open("qasm.lark", "r") as f:
    qasm_grammar = "".join(f.readlines())

qasm_parser = Lark(qasm_grammar, start="mainprogram")


def unpack(args):
    (args,) = args
    return args


def flatten(obj):
    if isinstance(obj, list):
        flat_list = []
        for item in obj:
            flat_list.extend(flatten(item))
        return flat_list
    elif isinstance(obj, NamedList):
        return flatten(obj.list)
    else:
        return [obj]


def flatten_recursive_list(*args):
    # flattens nested lists appearing in the AST
    args = unpack(args)
    return flatten(args)


def format_wires(wire_id_list):
    if len(wire_id_list) == 1:
        # <id>
        return wire_id_list[0]
    elif len(wire_id_list) == 2:
        # <id> [<nninteger>]
        return "{}[{}]".format(*wire_id_list)


NamedList = namedtuple("NamedList", ["name", "list"])


class Op:
    def __init__(self, name, params, wires, string):
        self.name = name
        self.params = params
        self.wires = wires
        self.string = string

    def __str__(self):
        return self.string


class Gate(Op):
    pass


class Term:
    def __init__(self, coeff, op):
        self.coeff = coeff
        self.op = op

    def __str__(self):
        return "{} {}".format(self.coeff, self.op)


class Declaration:
    def __init__(self, name, string, *args, **kwargs):
        self.name = name
        self.string = string
        self.args = args
        self.kwargs = kwargs

    def __str__(self):
        return self.string


class QDeclaration(Declaration):
    pass


class GateDeclaration(QDeclaration):
    pass


class OperatorDeclaration(QDeclaration):
    pass


class QASMToStringTransformer(Transformer):

    PI = lambda self, _: 3.14159
    sin = lambda self, _: sin
    cos = lambda self, _: cos
    tan = lambda self, _: tan
    exp = lambda self, _: exp
    ln = lambda self, _: log
    sqrt = lambda self, _: sqrt

    def mainprogram(self, *args):
        args = unpack(args)

        if len(args) == 1:
            program_str = args[0]
            header = ""
        else:
            version, program_str = args
            header = "OPENQASM {};".format(version)

        return "\n".join([header, program_str])

    def program(self, *args):
        args = flatten_recursive_list(*args)
        program_str = "\n".join(str(x) for x in args)
        return program_str

    def statement(self, *args):
        args = unpack(args)
        if isinstance(args[0], Declaration):
            # <decl>
            decl = args[0]
            s = str(decl)
            if isinstance(decl, QDeclaration):
                # <gatedecl> <goplist> } or
                # <gatedecl> } or
                # <opdecl> <goplist> } or
                # <opdecl> } or
                if len(args) == 2:
                    goplist = flatten(args[1])
                    s += "\n"
                    s += "\n".join("    " + str(x) for x in goplist)
                s += "\n}"
        elif args[0] == "opaque":
            # opaque <id> <idlist>; or
            # opaque <id> () <idlist>; or
            # opaque <id> (<idlist>) <idlist>;
            id_ = args[1]
            s = "opaque {}".format(id_)
            if len(args) == 4:
                bracket_idlist = args[2]
                bracket_idlist_str = ",".join(bracket_idlist.list)
                bracket_content = "({})".format(bracket_idlist_str)
                final_idlist = args[3]
            else:
                bracket_content = ""
                final_idlist = args[2]
            final_idlist_str = ",".join(final_idlist.list)
            s += "{} {};".format(bracket_content, final_idlist_str)
        elif isinstance(args[0], Op):
            s = str(args[0])
        elif args[0] == "if":
            # if ( <id> == <nninteger> ) <qop>
            id_, intval, op = args[1:]
            s = "if({}=={}) {}".format(id_, intval, op)
        elif args[0] == "barrier":
            # barrier <anylist>;
            barrier_list = ",".join([str(x) for x in flatten(args[1])])
            s = "barrier {};".format(barrier_list)

        elif args[0] == "include":
            with open(args[1][1:-1], "r") as f:
                included_file = "".join(f.readlines())

            tree = qasm_parser.parse(included_file)
            s = QASMToStringTransformer().transform(tree)
        return s

    def decl(self, *args):
        args = unpack(args)
        reg_type = str(args[0])
        id_, int_val = args[1:]
        s = "{} {}[{}];".format(reg_type, id_, int_val)
        d = Declaration(reg_type, string=s, id_=id_, int_val=int_val)
        return d

    def opdecl(self, *args):
        return self.qdecl("operator", OperatorDeclaration, *args)

    def gatedecl(self, *args):
        return self.qdecl("gate", GateDeclaration, *args)

    def qdecl(self, keyword, dataclass, *args):
        args = unpack(args)
        decl_name = str(args[0])
        id_ = args[1]
        idlist1 = flatten(args[2])
        if len(args) == 4:
            idlist2 = flatten(args[3])
        else:
            idlist2 = None

        if not idlist2:
            # gate <id> <idlist> { or
            # gate <id> ( ) <idlist> {
            kwargs = {"idlist": idlist1}
            idstr = ",".join(idlist1)
            s = "{} {} {}".format(keyword, id_, idstr) + " {"
        else:
            # gate <id> ( <idlist> ) <idlist> {
            kwargs = {"idlist1": idlist1, "idlist2": idlist2}
            idstr1 = ", ".join(idlist1)
            idstr2 = ", ".join(idlist2)
            s = "{} {} ({}) {}".format(keyword, id_, idstr1, idstr2) + " {"
        d = dataclass(decl_name, string=s, id_=id_, **kwargs)
        return d

    def goplist(self, *args):
        args = unpack(args)
        if len(args) == 1:
            # <uop>
            # <term>
            return NamedList("goplist", flatten(args))
        if "barrier" in args:
            if len(args) == 2:
                # barrier <idlist>;
                idlist = args[1]
                idlist_str = ",".join(str(x) for x in idlist.list)
                s = "barrier {};".format(idlist_str)
            else:
                # <goplist> barrier <idlist>;
                goplist = args[0]
                idlist = args[2]
                goplist_str = ",".join(str(x) for x in goplist.list)
                idlist_str = ",".join(str(x) for x in idlist.list)
                s = "{} barrier {};".format(goplist_str, idlist_str)
            return s
        if isinstance(args[0], NamedList):
            # <goplist> <uop> or
            # <goplist> <term>
            return NamedList("goplist", flatten(args))

    def term(self, *args):
        # <term>
        args = unpack(args)
        if len(args) == 2:
            coeff, op = args
        elif len(args) == 1:
            # only works because this is the only defined unary op appearing in a term
            coeff = -1
            op = args[0]
        t = Term(coeff, op)
        return flatten(t)

    def qop(self, *args):
        args = unpack(args)
        if len(args) == 1:
            # <uop>
            return args[0]
        elif args[0] == "reset":
            # reset <argument>;
            wires = format_wires(args[1].list)
            s = "reset {};".format(wires)
        elif args[0] == "measure":
            wires = [format_wires(x.list) for x in args[1:]]
            s = "measure {} -> {};".format(*wires)
        op = Op(name=args[0], params=[], wires=wires, string=s)
        return op

    def uop(self, *args):
        args = unpack(args)
        op_name = str(args[0])
        extra_args = args[1:]
        if op_name == "CX":
            # CX <argument>, <argument>;
            params = []
            wires = [format_wires(x.list) for x in extra_args]
            s = "CX {},{};".format(*wires)
        elif op_name == "U":
            # U (<explist>) <argument>;
            expressionlist, argument = extra_args
            params = expressionlist.list
            wires = format_wires(argument.list)
            param_str = ", ".join(str(e) for e in params)
            s = "U({}) {};".format(param_str, wires)
        else:
            # user-defined name
            if extra_args[0].name == "expressionlist":
                # <id>(<expressionlist>)<anylist>
                expressionlist, anylist = extra_args
                params = expressionlist.list
                wires = flatten(anylist)
                param_str = ",".join(str(e) for e in params)
                wires_str = ",".join(str(a) for a in wires)
                s = "{}({}) {};".format(op_name, param_str, wires_str)
            elif extra_args[0].name == "anylist":
                # <id><anylist>; or
                # <id>()<anylist>
                anylist = extra_args[0]
                params = []
                wires = flatten(anylist)
                wires_str = ",".join(str(a) for a in wires)
                s = "{} {};".format(op_name, wires_str)
        op = Gate(op_name, params, wires, string=s)
        return op

    def anylist(self, *args):
        # either <idlist> or <mixedlist>
        return NamedList("anylist", unpack(args))

    def idlist(self, *args):
        # either <id> or <idlist>, <id>
        flat_list = flatten_recursive_list(*args)
        return NamedList("idlist", flat_list)

    def mixedlist(self, *args):
        args = unpack(args)
        if isinstance(args[0], NamedList):
            # <mixedlist>, <id> or
            # <mixedlist>, <id> [<nninteger>] or
            # <idlist>, <id> [<nninteger>]
            list_ = args[0]
            extra_args = format_wires(args[1:])
            wires = flatten([list_, extra_args])
        else:
            # <id> [<nninteger>]
            wires = [format_wires(args)]
        return NamedList("mixedlist", wires)

    def argument(self, *args):
        args = unpack(args)
        # <id> or
        # <id>[<nninteger>]
        return NamedList("argument", args)

    def expressionlist(self, *args):
        flat_list = flatten_recursive_list(*args)
        return NamedList("expressionlist", flat_list)

    def expression(self, *args):
        args = unpack(args)
        if len(args) == 1:
            # numbers, ids, or resolved expressions, just need to flatten
            val = unpack(args)
        elif len(args) == 2:
            # unary ops
            f, x = args
            val = f(x)
        return val

    def add(self, expression):
        (lterm, rterm) = expression
        return lterm + rterm

    def subtract(self, expression):
        (lterm, rterm) = expression
        return lterm - rterm

    def multiply(self, expression):
        (lterm, rterm) = expression
        return lterm * rterm

    def divide(self, expression):
        (lterm, rterm) = expression
        return lterm / rterm

    def exponentiate(self, expression):
        (base, exponent) = expression
        return base ** exponent

    def negate(self, expression):
        (val,) = expression
        if isinstance(val, str):
            negval = "-" + val
        else:
            negval = -val
        return negval

    def id_(self, name):
        name = unpack(name)
        return name.value

    def real(self, args):
        return float(unpack(args))

    def nninteger(self, n):
        return int(unpack(n))

    def parameter(self, name):
        return sympy.Symbol(name[0])