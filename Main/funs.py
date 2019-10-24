# global modules
import numpy as np
import warnings
from numba import njit, prange
import time
from prettytable import PrettyTable
import matplotlib.pyplot as plt
import seaborn as sns
sns.set_style("whitegrid")

# consav
from consav import linear_interp

# local modules
import transitions


def GaussHermite(n):
    """ GaussHermite nodes and weights
    
    Args:
        n (int): number of nodes

    Returns:
        (tuple): nodes and weights
    """
    return np.polynomial.hermite.hermgauss(n)

def GaussHermite_lognorm(var, n):
    """ GaussHermite nodes and weights for lognormal shocks
    
    Args:
        sigma (double): standard deviation of underlying normal distribution
        n (int): number of nodes

    Returns:
        x,w (tuple): nodes and weights
    """    
    
    x,w = GaussHermite(n)
    sigma = np.sqrt(var)
    x = np.exp(x*np.sqrt(2)*sigma - 0.5*var)
    w = w/np.sqrt(np.pi)

    assert(1 - sum(w*x) < 1e-8)
    return x,w 

def GH_lognorm_corr(var_men,var_women,cov,Nxi_men,Nxi_women):
    """ GaussHermite nodes and weights for correlated lognormal shocks
    
    Args:
        sigma_men (double): standard deviation of underlying normal distribution for men
        sigma_women (double): standard deviation of underlying normal distribution for women        
        cov (double): covariance between shocks
        Nxi_men (int): number of nodes for men
        Nxi_women (int): number of nodes for women

    Returns:
        x1,x2,w (tuple): nodes for men, nodes for women and weights
    """    

    x1,w1 = GaussHermite(Nxi_men)
    x2,w2 = GaussHermite(Nxi_women)

    x1 = np.sqrt(2)*x1
    w1 = w1/np.sqrt(np.pi)
    x2 = np.sqrt(2)*x2
    w2 = w2/np.sqrt(np.pi) 
    
    mean1 = -0.5*var_men
    mean2 = -0.5*var_women

    cov_matrix = np.array(([var_men, cov], [cov, var_women]))
    chol = np.linalg.cholesky(cov_matrix)
    assert(np.allclose(cov_matrix[:], chol @ np.transpose(chol)))

    x1,x2 = np.meshgrid(x1,x2,indexing='ij')
    w1,w2 = np.meshgrid(w1,w2,indexing='ij')    
    x1,x2 = x1.ravel(),x2.ravel()
    w1,w2 = w1.ravel(),w2.ravel()

    x2 = np.exp(chol[1,0]*x1 + chol[1,1]*x2 + mean2)
    x1 = np.exp(chol[0,0]*x1 + mean1)
    w = w1*w2
    assert(np.allclose(np.sum(w),1))

    return x1,x2,w


@njit(parallel=True)
def logsum2(V, par):
    """ logsum for 2 choices
    
    Args:
        V (numpy.ndarray): choice specific value functions
        par (class): parameters

    Returns:
        logsum,prob (tuple): logsum and choice probabilities
    """    


    # 1. setup
    sigma = par.sigma_eta
    cols = V.shape[1]

    # 2. maximum over the discrete choices
    mxm = np.maximum(V[0,:],V[1,:]).reshape(1,cols)       

    # 3. logsum and probabilities
    if abs(sigma) > 1e-10:
        logsum = mxm + sigma*np.log(np.sum(np.exp((V - mxm*np.ones((1,cols)))/sigma),axis=0)).reshape(mxm.shape)
        prob = np.exp((V - logsum*np.ones((1,cols)))/sigma)

    else:
        logsum = mxm
        prob = np.zeros(V.shape)
        for i in range(cols):
            if V[0,i] >= mxm[:,i][0]:
                prob[0,i] = 1
            else:
                prob[1,i] = 1 

    return logsum,prob


@njit(parallel=True)
def logsum4(V, par):
    """ logsum for 4 choices
    
    Args:
        V (numpy.ndarray): choice specific value functions
        par (class): parameters

    Returns:
        logsum,prob (tuple): logsum and choice probabilities
    """      
    
    # 1. setup
    sigma = par.sigma_eta
    cols = V.shape[1]

    # 2. maximum over the discrete choices
    mxm = np.maximum(np.maximum(V[0,:],V[1,:]), np.maximum(V[2,:],V[3,:])).reshape(1,cols)
    # mxm = np.maximum(np.maximum(V[0,:],V[1,:],V[2,:]),V[3,:]).reshape(1,cols)   # max 3 args in maximum        

    # 3. logsum and probabilities
    if abs(sigma) > 1e-10:
        logsum = mxm + sigma*np.log(np.sum(np.exp((V - mxm*np.ones((1,cols)))/sigma),axis=0)).reshape(mxm.shape)
        prob = np.exp((V - logsum*np.ones((1,cols)))/sigma)

    else:
        logsum = mxm
        prob = np.zeros(V.shape)
        for i in range(cols):
            mx = mxm[:,i][0]
            if V[0,i] >= mx:
                prob[0,i] = 1
            elif V[1,i] >= mx:
                prob[1,i] = 1
            elif V[2,i] >= mx:
                prob[2,i] = 1
            else:
                prob[3,i]

    return logsum,prob



def resolve(model,**kwargs):
    """ resolve model and plot euler errors
    
    Args:
        model (class): solution, parameters and simulation
        kwargs (dict): resolves the model for the elements in the dict

    Returns:
        plot of euler errors
    """      
    
    x = []
    work = []
    whole = []
    
    for key,val in kwargs.items():
        for v in val:
            setattr(model.par,str(key),v)
            model.solve(recompute=True)
            model.simulate(recompute=True,accuracy=True)
            x.append(v)
            work.append(log_euler(model,ages=[57,77])[0])
            whole.append(log_euler(model,ages=[57,110-1])[0])  
            
    plt.plot(x,work,label='57-77')
    plt.plot(x,whole,label='whole period')
    plt.legend()


def log_euler(model,MA=[0,1],ST=[0,1,2,3],ages=[57,68],plot=False):
    """ log euler errors
    
    Args:
        model (class): solution, parameters and simulation
        MA (list): list with male indicator
        ST (list): list of states
        ages (list): start age and end age
        plot (bool): if True return a plot, if False return tuple

    Returns:
        if plot=True return plot else return tuple of euler errors
    """      

    # unpack
    sim = model.sim
    par = model.par
    
    # mask
    x = np.arange(ages[0], ages[1]+1)
    mask_t = transitions.inv_age(x,par)
    states = sim.states
    mask = np.nonzero(np.isin(states[:,1],ST))[0]
    if len(MA) == 1:
        mask = mask[states[:,0][mask]==MA]
    
    # euler errors
    euler = sim.euler[mask] # states
    euler = euler[:,mask_t] # time
    c = sim.c[mask]
    c = c[:,mask_t]
    log_abs = np.log10(abs(euler/c))
    
    # plot or return   
    total = np.nanmean(log_abs)
    with warnings.catch_warnings(): # ignore this specific warning
        warnings.simplefilter("ignore", category=RuntimeWarning)
        y = np.nanmean(log_abs,axis=0)    
    
    if plot:
        plt.plot(x,y)
    else:
        return total,x,y


def create_iterator(lst,num):
    indices = 0
                 
    if num == 3:
        iterator = np.zeros((len(lst[0])*len(lst[1])*len(lst[2]),num),dtype=int)        
        for x in lst[0]:
            for y in range(len(lst[1])):
                for z in range(len(lst[2])):
                    iterator[indices] = (x,y,z)
                    indices += 1
    
    return iterator


def my_timer(funcs,argu,names,Ntimes=100,unit='ms',ndigits=2):
    """ times functions
    
    Args:
        funcs (list): functions to be evaluated
        argu (dict): arguments to evaluate the functions in
        names (dict): names for printing
        Ntimes (int): number of times to evaluate the functions
        unit (str): unit to measure time
        ndigits (int): number of digits of timings

    Returns:
        (prettytable): timings
    """  

    # check if correct type
    if type(funcs) == list:
        pass
    else:
        funcs = [funcs]
    
    # allocate
    store = np.empty((Ntimes,len(funcs)))
    def run_func(f,*args,**kwargs):
        f(*args,**kwargs)    
        
    for i in range(len(funcs)): # loop over funcions
        for j in range(Ntimes): # loop over executions
            tic = time.time()
            run_func(funcs[i],*argu[funcs[i]])
            toc = time.time()
            store[j,i] = toc-tic
            
    out,unit = timings(funcs,names,store,Ntimes,unit,ndigits)
    print('time unit is:',unit)
    print(out)
        
def timings(funcs, names, store, Ntimes, unit, ndigits):     

    # prep
    header = ['func', 'lq', 'median', 'mean', 'uq', 'neval']
    
    # summary statistics
    summ = np.transpose(np.vstack(
                              (np.percentile(store, [25,50], axis=0), #lq, median
                               np.mean(store, axis=0),                      #mean
                               np.percentile(store, 75, axis=0))            #uq
                               ))              
    
    # format times
    factor = {'ms':1E3, 'us':1E6, 'ns':1E9, 's':1}
    summ = np.round(summ*factor[unit], ndigits)
    
    # add neval
    summ = np.hstack((summ, np.ones((len(funcs),1))*Ntimes))
    
    # create table
    out = PrettyTable(header)
    for i in range(len(funcs)):
        out.add_row([names[funcs[i]]]+(summ[i,:].tolist()))
    
    # output
    return out,unit