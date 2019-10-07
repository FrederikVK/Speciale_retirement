# global modules
from numba import njit, prange
import numpy as np

# consav
from consav import linear_interp
from consav import upperenvelope 

# local modules
import utility
import post_decision
import transitions

# upper envelope function
envelope = upperenvelope.create(utility.func)
envelope_c = upperenvelope.create(utility.func_c)

###############################
### Functions for singles #####
###############################
@njit(parallel=True)
def solve(t,ad,ma,st,ra,d,sol,par):
    """ wrapper which calls both post_decision.compute and egm.solve_bellman"""

    post_decision.compute(t,ad,ma,st,ra,d,sol,par)
    solve_bellman(t,ad,ma,st,ra,d,sol,par)  

@njit(parallel=True)
def solve_bellman(t,ad,ma,st,ra,D,sol,par):
    """ solve the bellman equation for singles using the endogenous grid method
    
    Args:
        t (int): model time
        ad (int): age difference, just zero here
        ma (int): 0 if female and 1 if male
        st (int): states
        ra (int): retirement status
        D (numpy.ndarray): choice set
        sol (class): solution
        par (class): parameters

    Returns:
        stores c,m,v in sol
    """    

    # unpack solution
    c = sol.c[t,ad,ma,st,ra]
    m = sol.m[t,ad,ma,st,ra]
    v = sol.v[t,ad,ma,st,ra]

    # unpack rest
    a = par.grid_a
    q = sol.q[:,:]
    v_plus_raw = sol.v_plus_raw[:,:]        
    pi_plus = transitions.survival_look_up(t+1,ma,par)   

    # loop over the choices
    for d in D:

        # a. raw solution
        c_raw = utility.inv_marg_func(q[d],par)
        m_raw = a + c_raw
        v_raw = par.beta*(pi_plus*v_plus_raw[d] + (1-pi_plus)*par.gamma*a)

        # b. upper envelope
        m[d] = a      
        envelope(a,m_raw,c_raw,v_raw,m[d],  # input
                 c[d],v[d],                 # output
                 d,ma,st,par)               # args for utility function  


###############################
### Functions for couples #####
###############################
@njit(parallel=True)
def solve_c(t,ad,st_h,st_w,ra_h,ra_w,D_h,D_w,sol,par,single_sol):
    """ wrapper which calls both post_decision.compute_c and egm.solve_bellman_c"""
        
    post_decision.compute_c(t,ad,st_h,st_w,ra_h,ra_w,D_h,D_w,sol,par)
    solve_bellman_c(t,ad,st_h,st_w,ra_h,ra_w,D_h,D_w,sol,par,single_sol)  

@njit(parallel=True)
def solve_bellman_c(t,ad,st_h,st_w,ra_h,ra_w,D_h,D_w,sol,par,single_sol):
    """ solve the bellman equation for couples using the endogenous grid method
    
    Args:
        t (int): model time
        ad (int): age difference, just zero here
        ma (int): 0 if female and 1 if male
        st (int): states
        ra (int): retirement status
        D_h (numpy.ndarray): choice set, husband
        D_w (numpy.ndarray): choice set, wife        
        sol (class): solution
        par (class): parameters

    Returns:
        stores c,m,v in sol
    """    

    # unpack solution
    ad_min = par.ad_min
    ad_idx = ad+ad_min
    c = sol.c[t,ad_idx,st_h,st_w,ra_h,ra_w]
    m = sol.m[t,ad_idx,st_h,st_w,ra_h,ra_w]
    v = sol.v[t,ad_idx,st_h,st_w,ra_h,ra_w]

    # unpack rest
    a = par.grid_a
    q = sol.q[:,:]
    v_plus_raw = sol.v_plus_raw[:,:]        
    pi_h,pi_w = transitions.survival_look_up_c(t+1,ad,par)   

    # loop over the choices
    for d_h in D_h:
        for d_w in D_w:

            # a. indices
            d = transitions.d_c(d_h,d_w)                    # joint index
            d_plus_h = transitions.d_plus_int(t,d_h,par)    # choice tomorrow
            d_plus_w = transitions.d_plus_int(t,d_w,par)    # choice tomorrow

            # b. looking up in single solution
            # VH = single_sol.v[t+1+ad_min,0,1,st_h,ra_h,d_plus_h]        # ad=0 and male=1
            # VW = np.zeros(VH.shape)     # initialize
            # if t+1+ad < par.T:          # wife alive
            #     VW[:] = single_sol.v[t+1+ad_idx,0,0,st_w,ra_w,d_plus_w] # ad=0 and male=0     
            VH = single_sol.v[t+ad_min,0,1,st_h,ra_h,d_plus_h]        # ad=0 and male=1
            VW = np.zeros(VH.shape)     # initialize
            if t+ad < par.T:          # wife alive
                VW[:] = single_sol.v[t+ad_idx,0,0,st_w,ra_w,d_plus_w] # ad=0 and male=0   


            # c. raw solution
            c_raw = utility.inv_marg_func(q[d],par)
            m_raw = a + c_raw
            # v_raw = par.beta*(pi_h*pi_w*v_plus_raw[d] +     # both alive
            #                 pi_h*(1-pi_w)*VH +              # husband alive -> look up in single solution
            #                 (1-pi_h)*pi_w*VW +              # wife alive -> look up in single solution
            #                 (1-pi_h)*(1-pi_w)*par.gamma*a)  # both dead
            v_raw = par.beta*(pi_h*pi_w*v_plus_raw[d] +     # both alive
                             (1-pi_h*pi_w)*par.gamma*a)  # both dead


            # d. upper envelope
            m[d] = a      
            envelope_c(a,m_raw,c_raw,v_raw,m[d],    # input
                    c[d],v[d],                      # output
                    d_h,d_w,st_h,st_w,par)          # args for utility function  