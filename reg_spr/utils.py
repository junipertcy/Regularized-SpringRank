import graph_tool.all as gt
import numpy as np
from numba import jit
from scipy.sparse import csr_matrix, csc_matrix
from scipy.sparse.linalg import inv
from itertools import combinations
from math import comb
from collections import Counter
from scipy.linalg import svd

from logging import getLogger

logger = getLogger(__name__)
# from numpy.random import default_rng
# import scipy.sparse


def compute_cache_from_g(g, alpha, sparse=True, regularization=True, ell=True):
    A = gt.adjacency(g)
    # print(f"our method: adj = {A.todense()[:5,:5]}")
    if A.shape[0] != A.shape[1]:
        raise ValueError("Are you sure that A is symmetric?")
    if type(A) not in [csr_matrix, csc_matrix]:
        raise TypeError(
            "Please make sure that A is of type `csr_matrix` or `csc_matrix` of scipy.sparse."
        )
    shape = A.shape[0]
    row = []
    col = []
    data = []
    row_b = []
    col_b = []
    data_b = []
    for ind in zip(*A.nonzero()):
        i, j = ind[0], ind[1]
        if i == j:
            logger.warning(
                "WARNING: self-loop detected in the adjacency matrix. Ignoring..."
            )
            continue
        if j < i:
            _row = i * (shape - 1) + j
        else:
            _row = i * (shape - 1) + j - 1
        row.append(_row)
        col.append(i)
        data.append(-A[ind] ** 0.5)
        # TODO: This should be right
        # But it doesn't match the math?
        # However, it is consistent with
        # bicgstab result in the original paper
        row.append(_row)
        col.append(j)
        data.append(A[ind] ** 0.5)

        row_b.append(_row)
        col_b.append(0)
        data_b.append(-A[ind] ** 0.5)

    if regularization:
        row += list(range(shape**2 - shape, shape**2))
        col += list(range(shape))
        data += [alpha**0.5] * shape
        row_b += list(range(shape**2 - shape, shape**2))
        col_b += [0] * shape
        data_b += [0] * shape
        B = csr_matrix((data, (row, col)), shape=(shape**2, shape), dtype=np.float64)
        b = csr_matrix(
            (data_b, (row_b, col_b)), shape=(shape**2, 1), dtype=np.float64
        )
    else:
        logger.warning("WARNING: no regularization is used. Are you sure?")
        B = csr_matrix(
            (data, (row, col)), shape=(shape**2 - shape, shape), dtype=np.float64
        )
        b = csr_matrix(
            (data_b, (row_b, col_b)), shape=(shape**2 - shape, 1), dtype=np.float64
        )

    if not sparse:
        B = B.todense()
        b = b.todense()

    if ell:
        _ell = compute_ell(g)
    else:
        _ell = None

    Bt_B_inv = compute_Bt_B_inv(B, sparse=0)

    _, s, Vh = svd(B.todense(), full_matrices=False)
    Bt_B_invSqrt = Vh.T @ np.diag(1 / s) @ Vh

    return {
        "B": B,
        "b": b,
        "ell": _ell,
        "Bt_B_inv": Bt_B_inv,
        "Bt_B_invSqrt": Bt_B_invSqrt,
    }


def compute_Bt_B_inv(B, sparse=True):
    if not sparse:
        B = B.todense()
        return np.linalg.inv(np.dot(B.T, B))
    return inv(np.dot(B.T, B))


def grad_g_star(B, b, v):
    return np.dot(compute_Bt_B_inv(B), v + np.dot(B.T, b))


def compute_ell(g, arg="class"):
    ctr_classes = Counter(g.vp[arg])
    len_classes = len(ctr_classes)
    # print(f"ctr_classes: {ctr_classes}")
    comb_classes = combinations(ctr_classes, 2)
    mb = list(g.vp[arg])
    ell = np.zeros([comb(len_classes, 2), len(g.get_vertices())])

    for idx, (i, j) in enumerate(comb_classes):
        for vtx in g.vertices():
            vtx = vtx.__int__()
            if mb[vtx] == i:
                ell[idx][vtx] = -ctr_classes[i] ** -1
            elif mb[vtx] == j:
                ell[idx][vtx] = ctr_classes[j] ** -1
            else:
                ell[idx][vtx] = 0
    return ell


def compute_spearman_correlation(g, s):
    return


def render_ijwt(
    path="./etc/prestige_reinforcement/data/PhD Exchange Network Data/PhD_exchange.txt",
    delimiter=" ",
):
    g = gt.Graph()
    eweight = g.new_ep("double")
    etime = g.new_ep("int")

    name2id = dict()
    time2id = dict()
    nameid = 0
    timeid = 0

    with open(path, "r") as f:
        for line in f:
            ijwt = line.replace("\n", "").split(delimiter)[:4]

            try:
                name2id[ijwt[0]]
            except KeyError:
                name2id[ijwt[0]] = nameid
                nameid += 1

            try:
                name2id[ijwt[1]]
            except KeyError:
                name2id[ijwt[1]] = nameid
                nameid += 1

            try:
                time2id[ijwt[3]]
            except KeyError:
                time2id[ijwt[3]] = timeid
                timeid += 1

            g.add_edge_list(
                [(name2id[ijwt[0]], name2id[ijwt[1]], ijwt[2], time2id[ijwt[3]])],
                eprops=[eweight, etime],
            )
    g.edge_properties["eweight"] = eweight
    g.edge_properties["etime"] = etime
    return g


def filter_by_time(g, time):
    mask_e = g.new_edge_property("bool")
    for edge in g.edges():
        if g.ep["etime"][edge] == time:
            mask_e[edge] = 1
        else:
            mask_e[edge] = 0
    return mask_e


def D_operator(s):
    # output = np.zeros(n**2)
    n = len(s)
    output = np.zeros(n**2 - n)  # if we avoid the zero rows
    k = 0
    for i in range(n):
        for j in range(i):
            output[k] = s[i] - s[j]
            k += 1
        # Avoid letting j = i since that's just s[i] - s[i] so it's a zero row
        for j in range(i + 1, n):
            output[k] = s[i] - s[j]
            k += 1
        # for j in range(n):
        #     # k = i + j*n
        #     output[k] = s[i] - s[j]
        #     k += 1
    return output


def D_operator_reg_t_sparse(a, s):
    if type(a) is not csr_matrix:
        raise TypeError("Please use a `csr_matrix` of scipy.sparse.")
    n = a.shape[0]
    output_t = np.zeros(n)  # if we avoid the zero rows

    for ind in zip(*a.nonzero()):
        i, j = ind[0], ind[1]
        if i < j:
            k = n * i + j - i - 1
        elif i > j:
            k = n * i + j - i

        output_t[i] += (a[i, j] ** 0.5) * s[k]
        output_t[j] -= (a[i, j] ** 0.5) * s[k]
    return output_t


@jit(nopython=True)
def D_operator_reg_t(a, s):
    n = len(a)
    output_t = np.zeros(n)  # if we avoid the zero rows
    k = 0
    for i in range(n):
        for j in range(i):
            output_t[i] += (a[i, j] ** 0.5) * s[k]
            output_t[j] -= (a[i, j] ** 0.5) * s[k]
            k += 1
        # Avoid letting j = i since that's just s[i] - s[i] so it's a zero row
        for j in range(i + 1, n):
            output_t[i] += (a[i, j] ** 0.5) * s[k]
            output_t[j] -= (a[i, j] ** 0.5) * s[k]
            k += 1
    return output_t


def D_operator_reg_sparse(a, s):
    if type(a) is not csr_matrix:
        raise TypeError("Please use a `csr_matrix` of scipy.sparse.")
    n = a.shape[0]
    output = np.zeros(n**2 - n)  # if we avoid the zero rows
    for ind in zip(*a.nonzero()):
        i, j = ind[0], ind[1]
        if i < j:
            k = n * i + j - i - 1
        elif i > j:
            k = n * i + j - i
        output[k] = (a[i, j] ** 0.5) * (s[i] - s[j])
    return output


@jit(nopython=True)
def D_operator_reg(a, s):
    n = len(a)
    output = np.zeros(n**2 - n)  # if we avoid the zero rows
    k = 0
    for i in range(n):
        for j in range(i):
            output[k] = (a[i, j] ** 0.5) * (s[i] - s[j])
            k += 1
        # Avoid letting j = i since that's just s[i] - s[i] so it's a zero row
        for j in range(i + 1, n):
            output[k] = (a[i, j] ** 0.5) * (s[i] - s[j])
            k += 1
    return output


def D_operator_b_sparse(a):
    if type(a) is not csr_matrix:
        raise TypeError("Please use a `csr_matrix` of scipy.sparse.")
    n = a.shape[0]
    output = np.zeros(n**2 - n)  # if we avoid the zero rows
    for ind in zip(*a.nonzero()):
        i, j = ind[0], ind[1]
        if i < j:
            k = n * i + j - i - 1
        elif i > j:
            k = n * i + j - i
        output[k] = a[ind] ** 0.5
    return output


@jit(nopython=True)
def D_operator_b(a):
    n = len(a)
    output = np.zeros(n**2 - n)  # if we avoid the zero rows
    # k = n
    k = 0
    for i in range(n):
        for j in range(i):
            output[k] = a[i, j] ** 0.5

            # raise Exception(i, j, k, n * i + j - i - 1)
            k += 1
        # Avoid letting j = i since that's just s[i] - s[i] so it's a zero row
        for j in range(i + 1, n):
            output[k] = a[i, j] ** 0.5
            k += 1
    return output


def implicit2explicit(f, a, m, n):
    """assumes f(x) is a linear operator (x has size n)
    so it can be represented f(x) = A*x for some matrix x
    (for now, assume A is square for simplicity)
    A = A * identity
    """
    e = np.zeros(n)  # length n vector
    A = np.zeros((m, n))  # (n ** 2 - n) x n matrix
    for i in range(n):
        # Loop over columns of identity
        e[i] = 1
        output = f(a, e)
        A[:, i] = output
        e[i] = 0
    return A
