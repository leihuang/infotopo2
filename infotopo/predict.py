"""
"""

from __future__ import absolute_import, division, print_function
import logging

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from infotopo.util import Series, Matrix



RDELTAP = 1e-3



class Predict(object):
    """
    """

    def __init__(self, f, Df=None, pids=None, yids=None, pdim=None, ydim=None, 
                 p0=None, rank=None, ptype='', prior=None, pred=None, **kwargs):
        """

        :param f: takes array-like (np.array, series, list, tuple, etc.) 
            as argument and returns np.array; stored as attribute _f
        :param Df: takes array-like as argument and returns np.array; 
            stored as attribute _Df
        :param prior: None or a callable
        """

        if pred is not None:
            f = pred._f
            Df = pred._Df
            p0 = pred._p0
            pids = pred.pids
            yids = pred.yids
            rank = pred.rank
            ptype = pred.ptype

        assert not (pids is None and pdim is None)
        assert not (yids is None and ydim is None)
        
        if pids is None:
            pids = ['p_%d'%i for i in range(1, pdim+1)]
        if yids is None:
            yids = ['y_%d'%i for i in range(1, ydim+1)]
        if pdim is None:
            pdim = len(pids)
        if ydim is None:
            ydim = len(yids)

        if p0 is None:
            p0 = [1] * pdim

        _f, _Df, _p0 = f, Df, np.array(p0)
        
        if _Df is None:
            logging.warn("Df not given; calculated using finite difference.")
            _Df = get_Df_fd(_f, rdeltap=RDELTAP)
        
        def f(p=None):
            """Broadens the call signature to allow for None as argument and
            returns a series.
            """
            if p is None:
                p = self.p0
            y = _f(p)
            return Series(y, index=self.yids)  # use attr hence updatable
        
        def Df(p=None):
            """Broadens the call signature to allow for None as argument and
            returns a matrix.
            """
            if p is None:
                p = self.p0
            jac = _Df(p)
            return Matrix(jac, index=self.yids, columns=self.pids) 

        self.f = f
        self.Df = Df
        self._f = _f
        self._Df = _Df
        self.pids = pids
        self.yids = yids
        self.pdim = pdim 
        self.ydim = ydim 
        self.p0 = Series(p0, pids)
        self._p0 = _p0
        self.rank = rank
        self.ptype = ptype
        self.prior = prior
        
        for k, v in kwargs.items():
            setattr(self, k, v)


    def __call__(self, p=None):
        return self.f(p=p)


    def __add__(self, other):
        """Concatenate the output: (f+g)(p) = (f(p),g(p))
        """
        assert self.pids == other.pids, "pids not the same"
        assert all(self.p0 == other.p0), "p0 not the same"

        if len(set(self.yids).intersection(set(other.yids))) > 0:
            logging.warn("The two preds have overlapping yids.")
        
        def _f(p):
            return np.concatenate((self._f(p), other._f(p)))
        
        def _Df(p):
            return np.concatenate((self._Df(p), other._Df(p)))
            

        pred = Predict(f=_f, Df=_Df, p0=self.p0, pids=self.pids, 
                       yids=self.yids+other.yids, ptype=self.ptype)
        return pred


    def get_in_logp(self):
        """Get a Prediction object in log parameters.
        """
        assert self.ptype == '', "not in bare parametrization"
        
        def _f_logp(logp):
            p = np.exp(logp)
            return self._f(p)
        
        def _Df_logp(logp):
            # d y/d logp = d y/(d p/p) = (d y/d p) * p
            p = np.array(np.exp(logp))
            return self._Df(p) * p

        logpids = map(lambda pid: 'log_'+pid, self.pids)
        logp0 = Series(np.log(self._p0), logpids)

        pred_logp = Predict(f=_f_logp, Df=_Df_logp, p0=logp0,
                            pids=logpids, yids=self.yids, ptype='logp')
        return pred_logp


    def get_sigma(self, p=None, errormodel='constant', constant_sigma=1, 
                  cv=0.1):
        """Calculate the error bars (sigmas) of data from the specified 
        *error model*; the default is a constant error bar of 1 (equivalent 
        to unweighted least square).
        
        :param errormodel: 'constant': constant sigma of sigma0 (default)                           
                           'cv': proportional to y by cv
                           'mixed': the max of error models 'constant' and 'cv'
        :param constant_sigma: constant sigma; default is 1
        :param cv: value of coefficient of variation 
            (if errormodel is 'cv' or 'mixed')
        """
        y = self.f(p)
        if errormodel == 'constant':
            sigma = Series([constant_sigma] * len(y), self.yids)
        if errormodel == 'cv':
            sigma = y * cv
        if errormodel == 'mixed':
            sigma = Series(np.max((y*cv, [constant_sigma]*len(y)), axis=0),
                                self.yids)
        return sigma


    def get_dat(self, p=None, **kwargs):
        """
        :param p:
        :param kwargs: kwargs of Predict.get_sigma
        """
        return pd.DataFrame(np.transpose([self.f(p), 
                                          self.get_sigma(p, **kwargs)]), 
                            index=self.yids, columns=['Y','sigma'])


    def scale(self):
        """
        """
        raise NotImplementedError


    def currying(self):
        """
        """
        raise NotImplementedError


    def get_spectrum(self, p=None):
        """
        """
        if p is None:
            p = self.p0
        return np.linalg.svd(self._Df(p), compute_uv=False)


    def plot_spectra(self, ps=None, filepath='', figsize=None, figtitle='',
                     ylim=None, xylabels=None, subplots_adjust=None, 
                     plot_tol=False):
        """

        :param ps: a list of parameter vectors
        :param plot_tol: bool; if True, plot the threshold for numerical zero 
        """
        if ps is None:
            ps = [self.p0]
        
        m, n = len(ps), len(ps[0])
        
        if figsize is None:
            figsize = (2*m, 2*n**0.8)
            
        fig = plt.figure(figsize=figsize)
        ax = fig.add_subplot(111)

        for idx, p in enumerate(ps):
            sigmas = self.get_spectrum(p)
            for sigma in sigmas:
                ax.plot([idx+0.1, idx+0.9], [sigma, sigma], c='k')
            if plot_tol:
                tol = sigmas[0] * max(len(self.pids), len(self.yids)) *\
                    np.finfo(sigmas.dtype).eps
                ax.plot([idx+0.1, idx+0.9], [tol, tol], c='r')
            ax.set_yscale('log')

        if ylim:
            ax.set_ylim(xylims[1])
        if xylabels:
            ax.set_xlabel(xylabels[0])
            ax.set_ylabel(xylabels[1])
        
        if subplots_adjust:
            plt.subplots_adjust(**subplots_adjust)
        
        plt.title(figtitle) 
        
        plt.savefig(filepath)
        plt.show()
        plt.close()



def get_Df_fd(f, rdeltap=None):
    """Get jacobian of f through symmetric finite difference
        
    :param rdeltap: relative delta param
    """
    if rdeltap is None:
        rdeltap = RDELTAP
    
    def _Df(p):
        jacT = []  # jacobian matrix transpose
        for i, p_i in enumerate(p):
            deltap_i = max(p_i * rdeltap, rdeltap)
            deltap = np.zeros(len(p))
            deltap[i] = deltap_i
            p_plus = p + deltap
            p_minus = p - deltap
            jacT.append((f(p_plus) - f(p_minus))/ 2 / deltap_i)
        jac = np.transpose(jacT)
        return jac
    return _Df



mathsubs = dict(sqrt=np.sqrt, exp=np.exp, log=np.log,
                Sqrt=np.sqrt, Exp=np.exp, Log=np.log,
                arctan=np.arctan, atan=np.arctan,
                sin=np.sin, cos=np.cos,
                pi=np.pi)



def str2predict(funcstr, pids, uids, us, c=None, p0=None, yids=None):
    """
    
    :param s:
    :param us: a list of u's where each u has the same length as uids and has the 
            same order
    :param c: if given, a mapping from convarid to convarval 

    >>> pred = str2predict('V*x/(K+x)', pids=['V','K'], uids=['x'], 
                           us=[[1],[2],[3]])
    """
    if c is not None:
        funcstr = util.sub_expr(funcstr, c)
    
    ystr = str([util.sub_expr(funcstr, dict(zip(uids, u))) for u in us]).\
        replace("'", "")
    ycode = compile(ystr, '', 'eval')
    
    def f(p):
        return np.array(eval(ycode, dict(zip(pids, p)), mathsubs))
    
    jaclist = []
    for u in us:
        funcstr_u = util.sub_expr(funcstr, dict(zip(uids, u)))
        jacrow = [util.simplify_expr(util.diff_expr(funcstr_u, pid)) 
                  for pid in pids]
        jaclist.append(jacrow)
    jacstr = str(jaclist).replace("'", "")
    jaccode = compile(jacstr, '', 'eval')

    def Df(p):
        return np.array(eval(jaccode, dict(zip(pids, p)), mathsubs))
    
    if p0 is None:
        p0 = [1] * len(pids)
    
    if yids is None:
        yids = ['u=%s'%str(list(u)) for u in us]
        
    return Predict(f=f, Df=Df, p0=p0, pids=pids, yids=yids)



def list2predict(funcstrs, pids, uids=None, us=None, yids=None, c=None, p0=None):
    """

    >>> pred = list2predict(['exp(-p1*1)+exp(-p2*1)', 
                             'exp(-p1*2)+exp(-p2*2)', 
                             'exp(-p1*1)-exp(-p2*1)'],
                            pids=['p1','p2'], p0=[1,2])
    
    >>> pred = list2predict(['(k1f*C1-k1r*X1)-(k2f*X1-k2r*X2)', 
                             '(k2f*X1-k2r*X2)-(k3f*X2-k3r*C2)'],
                            uids=['X1','X2'],
                            us=util.get_product([1,2,3],[1,2,3]),
                            pids=['k1f','k1r','k2f','k2r','k3f','k3r'], 
                            c={'C1':2,'C2':1})
                        
    Input:
        c: a mapping
    """
    if c is not None:
        funcstrs = [util.sub_expr(funcstr, c) for funcstr in funcstrs]
    
    if uids is not None:
        funstrs = [[util.sub_expr(funcstr, dict(zip(uids, u))) for u in us] 
                   for funstr in funstrs]
        funstrs = util.flatten(funstrs)
    
    ystr = str(funstrs).replace("'", "")
    ycode = compile(ystr, '', 'eval')
    
    def f(p):
        return np.array(eval(ycode, dict(zip(pids, p)), mathsubs))
    
    jaclist = []
    for funstr in funstrs:
        jacrow = [util.simplify_expr(util.diff_expr(funstr, pid))
                  for pid in pids]
        jaclist.append(jacrow)
    jacstr = str(jaclist).replace("'", "")
    jaccode = compile(jacstr, '', 'eval')

    def Df(p):
        return np.array(eval(jaccode, dict(zip(pids, p)), mathsubs))
    
    if p0 is None:
        p0 = [1] * len(pids)
        
    if yids is None:
        yids = ['y%d'%(i+1) for i in range(len(funstrs))]
        
    return Predict(f=f, Df=Df, p0=p0, pids=pids, yids=yids)



def list2predict2(funcstrs, pids, uids=None, us=None, yids=None, c=None, 
                  p0=None):
    """
    """
    if c is not None:
        funcstrs = [util.sub_expr(funcstr, c) for funcstr in funcstrs]
    
    ystr = str(funcstrs).replace("'", "")
    ycode = compile(ystr, '', 'eval')
    
    def f(p):
        return np.array(eval(ycode, dict(zip(pids, p)), mathsubs))
    
    jaclist = []
    for funcstr in funcstrs:
        jacrow = [util.simplify_expr(util.diff_expr(s, pid)) for pid in pids]
        jaclist.append(jacrow)
        
    if us is not None:
        jaclist = [[[util.sub_expr(jacentry, dict(zip(uids, u))) 
                     for jacentry in jacrow] 
                    for jacrow in jaclist]
                   for u in us]
        jaclist = util.flatten(jaclist, depth=1)       

    jacstr = str(jaclist).replace("'", "")
    jaccode = compile(jacstr, '', 'eval')

    def Df(p):
        return np.array(eval(jaccode, dict(zip(pids, p)), mathsubs))
    
    if p0 is None:
        p0 = [1] * len(pids)
        
    if yids is None:
        yids = ['y%d'%i for i in range(1, len(funcstrs)+1)]
        if us is not None:
            uids = ['u%d'%i for i in range(1, len(us)+1)]
            yids = util.get_product(yids, uids)
        
    return Predict(f=f, Df=Df, p0=p0, pids=pids, yids=yids)    



