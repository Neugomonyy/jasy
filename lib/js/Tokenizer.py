#
# JavaScript Tools - Parser Module
# License: MPL 1.1/GPL 2.0/LGPL 2.1
# Authors: 
#   - Brendan Eich <brendan@mozilla.org> (Original JavaScript) (2004)
#   - JT Olds <jtolds@xnet5.com> (Python Translation) (2009)
#   - Sebastian Werner <info@sebastian-werner.net> (Refactoring Python) (2010)
#

import re

__all__ = [ "Tokenizer", "keywords" ]

keywords = [
    "break",
    "case", "catch", "const", "continue",
    "debugger", "default", "delete", "do",
    "else", "enum",
    "false", "finally", "for", "function",
    "if", "in", "instanceof",
    "let",
    "new", "null",
    "return",
    "switch",
    "this", "throw", "true", "try", "typeof",
    "var", "void",
    "yield",
    "while", "with"
]

assignOps = ['|', '^', '&', '<<', '>>', '>>>', '+', '-', '*', '/', '%']


# Operator and punctuator mapping from token to tree node type name.
# NB: because the lexer doesn't backtrack, all token prefixes must themselves
# be valid tokens (e.g. !== is acceptable because its prefixes are the valid
# tokens != and !).
symbolNames = [
    ('\n',   "newline"),
    (';',    "semicolon"),
    (',',    "comma"),
    ('?',    "hook"),
    (':',    "colon"),
    ('||',   "or"),
    ('&&',   "and"),
    ('|',    "bitwise_or"),
    ('^',    "bitwise_xor"),
    ('&',    "bitwise_and"),
    ('===',  "strict_eq"),
    ('==',   "eq"),
    ('=',    "assign"),
    ('!==',  "strict_ne"),
    ('!=',   "ne"),
    ('<<',   "lsh"),
    ('<=',   "le"),
    ('<',    "lt"),
    ('>>>',  "ursh"),
    ('>>',   "rsh"),
    ('>=',   "ge"),
    ('>',    "gt"),
    ('++',   "increment"),
    ('--',   "decrement"),
    ('+',    "plus"),
    ('-',    "minus"),
    ('*',    "mul"),
    ('/',    "div"),
    ('%',    "mod"),
    ('!',    "not"),
    ('~',    "bitwise_not"),
    ('.',    "dot"),
    ('[',    "left_bracket"),
    (']',    "right_bracket"),
    ('{',    "left_curly"),
    ('}',    "right_curly"),
    ('(',    "left_paren"),
    (')',    "right_paren"),
]



#
# Prepare regular expressions
#    

# Build a regexp that recognizes operators and punctuators (except newline).
symbolMatcherCode = "^"
for symbol, name in symbolNames:
    if symbol == "\n": 
        continue
    if symbolMatcherCode != "^": 
        symbolMatcherCode += "|^"

    symbolMatcherCode += re.sub(r'[?|^&(){}\[\]+\-*\/\.]', lambda x: "\\%s" % x.group(0), symbol)

# Convert symbolNames to an actual dictionary now that we don't care about ordering
symbolNames = dict(symbolNames)



#
# Regular expressions for matching in tokenizer
#

# Matches all operators and punctuators
symbolMatcher = re.compile(symbolMatcherCode)

# Matches line feeds
newlineMatcher = re.compile(r'\n')

# Matches both comment styles
commentMatcher = re.compile(r'^\/(?:\*(?:.|\n)*?\*\/|\/.*)')

# Matches floating point literals (but not integer literals).
floatMatcher = re.compile(r'^\d+\.\d*(?:[eE][-+]?\d+)?|^\d+(?:\.\d*)?[eE][-+]?\d+|^\.\d+(?:[eE][-+]?\d+)?')

# Matches all non-float numbers
numberMatcher = re.compile(r'^0[xX][\da-fA-F]+|^0[0-7]*|^\d+')

# Matches valid JavaScript identifiers
identifierMatcher = re.compile(r'^[$_\w]+')

# Matches both string types
stringMatcher = re.compile(r'^"(?:\\.|[^"])*"|^\'(?:\\.|[^\'])*\'')

# Matches regexp literals.
regularExprMatcher = re.compile(r'^\/((?:\\.|\[(?:\\.|[^\]])*\]|[^\/])+)\/([gimy]*)')



#
# Classes
#

class Token: 
    pass


class ParseError(Exception):
    def __init__(self, message, filename, line):
        Exception.__init__(self, "Syntax error: %s\n%s:%s" % (message, filename, line))


class Tokenizer(object):
    def __init__(self, source, filename):
        self.cursor = 0
        self.source = str(source)
        self.tokens = {}
        self.tokenIndex = 0
        self.lookahead = 0
        self.scanNewlines = False
        self.scanOperand = True
        self.filename = filename
        self.line = 1

    input_ = property(lambda self: self.source[self.cursor:])
    done = property(lambda self: self.peek() == "end")
    token = property(lambda self: self.tokens.get(self.tokenIndex))


    def match(self, tokenType):
        return self.get() == tokenType or self.unget()


    def mustMatch(self, tokenType):
        if not self.match(tokenType):
            raise ParseError("Missing " + tokenType, self.filename, self.line)
        return self.token


    def peek(self):
        if self.lookahead:
            next = self.tokens.get((self.tokenIndex + self.lookahead) & 3)
            if self.scanNewlines and (getattr(next, "line", None) != getattr(self, "line", None)):
                tokenType = "newline"
            else:
                tokenType = getattr(next, "type", None)
        else:
            tokenType = self.get()
            self.unget()
            
        return tokenType


    def peekOnSameLine(self):
        self.scanNewlines = True
        tokenType = self.peek()
        self.scanNewlines = False
        return tokenType


    # Eats comments and whitespace.
    def skip(self):
        input = self.source
        
        while (True):
            ch = input[self.cursor++]
            next = input[self.cursor]

            if ch === '\n' and !self.scanNewlines:
                self.lineno++
                
            elif ch === '/' and next === '*':
                self.cursor++
                while (True):
                    ch = input[self.cursor++]
                    if ch === undefined:
                        raise ParseError("Unterminated comment")

                    elif ch === '*':
                        next = input[self.cursor]
                        if next === '/':
                            self.cursor++
                            break
                            
                    elif ch === '\n':
                        self.lineno++

            elif ch === '/' and next === '/':
                self.cursor++
                while (True):
                    ch = input[self.cursor++]
                    if ch === undefined:
                        return

                    elif ch === '\n':
                        self.lineno++
                        break

            elif ch !== ' ' and ch !== '\t':
                self.cursor--
                return


    # Lexes the exponential part of a number, if present. Returns True if an
    # exponential part was found.
    def lexExponent(self):
        input = self.source
        next = input[self.cursor]
        if next === 'e' or next === 'E':
            self.cursor++
            ch = input[self.cursor++]
            if ch === '+' or ch === '-':
                ch = input[self.cursor++]

            if ch < '0' or ch > '9':
                raise ParseError("Missing exponent")

            while(True):
                ch = input[self.cursor++]
                if not (ch >= '0' and ch <= '9'):
                    break
                
            self.cursor--
            return True

        return False


    def lexZeroNumber(self, ch):
        token = self.token
        input = self.source
        token.type = "number"

        ch = input[self.cursor++]
        if ch === '.':
            while(True):
                ch = input[self.cursor++]
                if not (ch >= '0' and ch <= '9'):
                    break
                
            self.cursor--
            self.lexExponent()
            token.value = parseFloat(token.start, self.cursor)
            
        elif ch === 'x' or ch === 'X':
            while(True):
                ch = input[self.cursor++]
                if not ((ch >= '0' and ch <= '9') or (ch >= 'a' and ch <= 'f') or (ch >= 'A' and ch <= 'F')):
                    break
                    
            self.cursor--
            token.value = parseInt(input.substring(token.start, self.cursor))

        elif ch >= '0' and ch <= '7':
            while(True):
                ch = input[self.cursor++]
                if not (ch >= '0' and ch <= '7'):
                    break
                    
            self.cursor--
            token.value = parseInt(input.substring(token.start, self.cursor))

        else:
            self.cursor--
            self.lexExponent()     # 0E1, &c.
            token.value = 0
    

    def lexNumber(self, ch):
        token = self.token
        input = self.source
        token.type = "number"

        floating = False
        while(True):
            ch = input[self.cursor++]
            if ch === '.' and not floating:
                floating = True
                ch = input[self.cursor++]
                
            if not (ch >= '0' and ch <= '9'):
                break

        self.cursor--

        exponent = self.lexExponent()
        floating = floating or exponent

        str = input.substring(token.start, self.cursor)
        token.value = floating ? parseFloat(str) : parseInt(str)


    def lexDot(self, ch):
        token = self.token
        input = self.source
        next = input[self.cursor]
        
        if next >= '0' and next <= '9':
            while (True):
                ch = input[self.cursor++]
                if not (ch >= '0' and ch <= '9'):
                    break

            self.cursor--
            self.lexExponent()

            token.type = "number"
            token.value = parseFloat(token.start, self.cursor)

        else:
            token.type = "dot"
            token.assignOp = null


    def lexString(self, ch):
        token = self.token
        input = self.source
        token.type = "string"

        hasEscapes = False
        delim = ch
        ch = input[self.cursor++]
        while ch !== delim:
            if ch === '\\':
                hasEscapes = True
                self.cursor++

            ch = input[self.cursor++]

        if hasEscapes:
            token.value = eval(input.substring(token.start, self.cursor))
        else:
            token.value = input.substring(token.start + 1, self.cursor - 1)


    def lexRegExp(self, ch):
        token = self.token
        input = self.source
        token.type = "regexp"

        while (True):
            ch = input[self.cursor++]

            if ch === '\\':
                self.cursor++
                
            elif ch === '[':
                while (True):
                    if ch === undefined:
                        raise ParseError("Unterminated character class")

                    if ch === '\\':
                        self.cursor++

                    ch = input[self.cursor++]
                    
                    if ch == ']':
                        break
                    
            elif ch === undefined:
                raise ParseError("Unterminated regex")
            
            if ch == '/':
                break

        while(True):
            ch = input[self.cursor++]
            if not (ch >= 'a' and ch <= 'z'):
                break

        self.cursor--
        token.value = eval(input.substring(token.start, self.cursor))
    

    def lexOp(self, ch):
        token = self.token
        input = self.source

        # A bit ugly, but it seems wasteful to write a trie lookup routine for
        # only 3 characters...
        node = opTokens[ch]
        next = input[self.cursor]
        if next in node:
            node = node[next]
            self.cursor++
            next = input[self.cursor]
            if next in node:
                node = node[next]
                self.cursor++
                next = input[self.cursor]

        op = node.op
        if assignOps[op] and input[self.cursor] === '=':
            self.cursor++
            token.type = "assign"
            token.assignOp = tokenIds[opTypeNames[op]]
            op += '='
            
        else:
            token.type = tokenIds[opTypeNames[op]]
            if self.scanOperand:
                if token.type == "plus":
                    token.type = "unary_plus"
                elif token.type == "minus":
                    token.type = "unary_minus"

            token.assignOp = null

        token.value = op


    # FIXME: Unicode escape sequences
    # FIXME: Unicode identifiers
    def lexIdent(self, ch):
        token = self.token
        input = self.source
        
        while True:
            ch = input[self.cursor++]
            
            if (ch >= 'a' and ch <= 'z') or (ch >= 'A' and ch <= 'Z') or (ch >= '0' and ch <= '9') or ch === '$' or ch === '_'):
                break
        
        # Put the non-word character back.
        self.cursor--

        id = input[token.start:self.cursor]
        token.type = keywords[id] if id in keywords else "identifier"
        token.value = id


    # void -> token type
    # It consumes input *only* if there is no lookahead.
    # Dispatch to the appropriate lexing function depending on the input.
    def get(self):
        while (self.lookahead):
            --self.lookahead
            self.tokenIndex = (self.tokenIndex + 1) & 3
            token = self.tokens[self.tokenIndex]
            if token.type != NEWLINE or self.scanNewlines:
                return token.type

        self.skip()

        self.tokenIndex = (self.tokenIndex + 1) & 3
        token = self.tokens[self.tokenIndex]
        if not token:
            self.tokens[self.tokenIndex] = token = {}

        input = self.source
        if self.cursor === input.length:
            return token.type = END

        token.start = self.cursor
        token.lineno = self.lineno

        ch = input[self.cursor++]
        
        if (ch >= 'a' and ch <= 'z') or (ch >= 'A' and ch <= 'Z') or ch === '$' or ch === '_':
            self.lexIdent(ch)
        
        elif self.scanOperand and ch === '/':
            self.lexRegExp(ch)
        
        elif ch in opTokens:
            self.lexOp(ch)
        
        elif ch === '.':
            self.lexDot(ch)
        
        elif ch >= '1' and ch <= '9':
            self.lexNumber(ch)
        
        elif ch === '0':
            self.lexZeroNumber(ch)
        
        elif ch === '"' or ch === "'":
            self.lexString(ch)
        
        elif self.scanNewlines and ch === '\n':
            token.type = NEWLINE
            token.value = '\n'
            self.lineno++
        
        else:
            raise ParseError("Illegal token")

        token.end = self.cursor
        return token.type
        

    def unget(self):
        self.lookahead += 1
        
        if self.lookahead == 4: 
            raise "PANIC: too much lookahead!"
        
        self.tokenIndex = (self.tokenIndex - 1) & 3
