#!/usr/bin/env python3
import base64
import math
import optparse
import random
from argparse import ArgumentError
from pyasn1.codec.der import encoder    # pip install pyasn1
from pyasn1.type.univ import Integer, Sequence

PEM_TEMPLATE = '-----BEGIN RSA PRIVATE KEY-----\n{}-----END RSA PRIVATE KEY-----\n'
DEFAULT_EXP = 65537


def is_prime(n, k=5):  # miller-rabin
    """
    https://stackoverflow.com/questions/36522167/checking-primality-of-very-large-numbers-in-python
    :param n: Number to test
    :param k: random trials
    :return: boolean
    """
    if n < 2:
        return False
    for p in [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]:
        if n % p == 0:
            return n == p
    s, d = 0, n - 1
    while d % 2 == 0:
        s, d = s + 1, d // 2
    for i in range(k):
        x = pow(random.randint(2, n - 1), d, n)
        if x == 1 or x == n - 1:
            continue
        for r in range(1, s):
            x = (x * x) % n
            if x == 1:
                return False
            if x == n - 1:
                break
        else:
            return False
    return True


def egcd(a, b):
    if a == 0:
        return b, 0, 1
    else:
        g, y, x = egcd(b % a, a)
        return g, x - (b // a) * y, y


def modinv(a, m):
    g, x, y = egcd(a, m)
    if g != 1:
        raise Exception('modular inverse does not exist')
    else:
        return x % m


def factor_modulus(n, d, e):
    """
    Efficiently recover non-trivial factors of n

    See: Handbook of Applied Cryptography
    8.2.2 Security of RSA -> (i) Relation to factoring (p.287)

    http://www.cacr.math.uwaterloo.ca/hac/
    """
    t = (e * d - 1)
    s = 0
    maxit = 2000

    while True:
        quotient, remainder = divmod(t, 2)

        if remainder != 0:
            break

        s += 1
        t = quotient

    found = False
    c1 = 0
    while not found and maxit > 0:
        i = 1
        a = random.randint(1, n - 1)

        while i <= s and not found:
            c1 = pow(a, pow(2, i - 1, n) * t, n)
            c2 = pow(a, pow(2, i, n) * t, n)
            found = c1 != 1 and c1 != (-1 % n) and c2 == 1
            i += 1
            maxit -= 1

    if maxit == 0:
        return None, None
    p = math.gcd(c1 - 1, n)
    q = n // p

    return p, q


def parts(s, l):
    return '\n'.join([s[i:i + l] for i in range(0, len(s), l)])


class RSA:
    def __init__(self, p=None, q=None, n=None, d=None, e=DEFAULT_EXP):
        """
        Initialize RSA instance using primes (p, q)
        or modulus and private exponent (n, d)
        """

        self.e = e

        if p and q:
            assert is_prime(p), 'p is not prime'
            assert is_prime(q), 'q is not prime'

            self.p = p
            self.q = q
        elif n and d:
            self.p, self.q = factor_modulus(n, d, e)
            if self.p is None or self.e is None:
                raise ArgumentError(None, 'Impossible to calculate p and q, check values')
        else:
            raise ArgumentError(None, 'Either (p, q) or (n, d) must be provided')

        self._calc_values()

    def _calc_values(self):
        self.n = self.p * self.q

        if self.p != self.q:
            phi = (self.p - 1) * (self.q - 1)
        else:
            phi = (self.p ** 2) - self.p

        self.d = modinv(self.e, phi)

        # CRT-RSA precomputation
        self.dP = self.d % (self.p - 1)
        self.dQ = self.d % (self.q - 1)
        self.qInv = modinv(self.q, self.p)

    def to_pem(self):
        """
        Return OpenSSL-compatible PEM encoded key
        """
        return PEM_TEMPLATE.format(base64.encodebytes(self.to_der()).decode()).encode()

    def to_der(self):
        """
        Return parameters as OpenSSL compatible DER encoded key
        """
        seq = Sequence()
        i = 0
        for x in [0, self.n, self.e, self.d, self.p, self.q, self.dP, self.dQ, self.qInv]:
            seq.setComponentByPosition(i, Integer(x))
            i += 1
        return encoder.encode(seq)

    def dump(self, verbose):
        dvars = ['n', 'e', 'd', 'p', 'q']

        if verbose:
            dvars += ['dP', 'dQ', 'qInv']

        for v in dvars:
            self._dumpvar(v)

    def _dumpvar(self, var):
        val = getattr(self, var)
        if type(val) is not Integer:
            val = int(val)

        if len(str(val)) <= 40:
            print('{0} = {1} ({1:#x})\n'.format(var, val))
        else:
            print('{} ='.format(var))
            print(parts('{:#x}'.format(val), 80) + '\n')


if __name__ == '__main__':
    parser = optparse.OptionParser()

    parser.add_option('-p', dest='p', help='prime', type='int')
    parser.add_option('-q', dest='q', help='prime', type='int')
    parser.add_option('-n', dest='n', help='modulus', type='int')
    parser.add_option('-d', dest='d', help='private exponent', type='int')
    parser.add_option('-e', dest='e', help='public exponent (default: %d)' % DEFAULT_EXP, type='int',
                      default=DEFAULT_EXP)
    parser.add_option('-o', dest='filename', help='output filename')
    parser.add_option('-f', dest='format', help='output format (DER, PEM) (default: PEM)', type='choice',
                      choices=['DER', 'PEM'], default='PEM')
    parser.add_option('-v', dest='verbose', help='also display CRT-RSA representation', action='store_true',
                      default=False)

    try:
        (options, args) = parser.parse_args()

        if options.p and options.q:
            print('Using (p, q) to initialise RSA instance\n')
            rsa = RSA(p=options.p, q=options.q, e=options.e)
        elif options.n and options.d:
            print('Using (n, d) to initialise RSA instance\n')
            rsa = RSA(n=options.n, d=options.d, e=options.e)
        else:
            parser.print_help()
            parser.error('Either (p, q) or (n, d) needs to be specified')

        rsa.dump(options.verbose)

        if options.filename:
            print('Saving {} as {}'.format(options.format, options.filename))

            if options.format == 'PEM':
                data = rsa.to_pem()
            elif options.format == 'DER':
                data = rsa.to_der()

            fp = open(options.filename, 'wb')
            fp.write(data)
            fp.close()

    except optparse.OptionValueError as ex:
        parser.print_help()
        parser.error(ex.msg)
