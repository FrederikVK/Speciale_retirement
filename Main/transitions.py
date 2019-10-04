# global modules
import numpy as np
from numba import njit, prange


##################################
####      index functions    #####
##################################
@njit(parallel=True)
def age(t,par): 
    """ compute real age (age) from model time (t). (The inverse of inv_age function)

    Args:
        t (int): model time
        par (class): contains information for the computation
    
    Returns:
        (int): real age
    """
    return t+par.start_T

@njit(parallel=True)
def inv_age(age,par): 
    """ compute model time from real age. (The inverse of age function)

    Args:
        age (int): real age
        par (class): contains information for the computation
    
    Returns:
        (int): model time
    """
    return age-par.start_T


@njit(parallel=True)
def ra_look_up(t,st,ra,d,par):
    """ compute the relevant retirement status if the agent is retired at t"""

    if state_translate(st,'elig',par) == 0:
        ra_look = 2

    elif d == 0:
        if t >= inv_age(par.oap_age,par)-1:
            ra_look = 0
        else:
            ra_look = ra

    elif d == 1:
        if t+1 >= inv_age(par.two_year,par):
            ra_look = 0
        elif t+1 >= inv_age(par.erp_age,par):
            ra_look = 1
        else:
            ra_look = 2

    return ra_look

@njit(parallel=True)
def d_plus(t,d_t,par):
    
    if d_t == 0:
        d_plus = np.array([0])
    elif d_t == 1:
        if t+1 == par.Tr-1:
            d_plus = np.array([0])
        elif t+1 < par.Tr-1:
            d_plus = np.array([0,1])

    return d_plus    

@njit(parallel=True)
def d_plus_c(t,ad,d,par):
    """ finds the choice set tomorrow for couples

    Args:
        t (int): model time
        ad (str): age difference = age of wife - age of husband
        d (int): choice/labor market status today
        par (class): parameters
    
    Returns:
        d_plus (numpy.ndarray): choice set tomorrow
    """
    # both retired
    if d == 0:  
        d_plus = np.array([0])

    # husband retired, wife working
    elif d == 1:
        if t+1+ad == par.Tr-1:  # wife forced to retire next period
            d_plus = np.array([0,0])
        else:
            d_plus = np.array([0,1]) 

    # husband working, wife retired
    elif d == 2:
        if t+1 == par.Tr-1:     # husband forced to retire next period
            d_plus = np.array([0,0])
        else:
            d_plus = np.array([0,2])    

    # both working
    elif d == 3:
        if ad == 0 and t+1 == par.Tr-1:     # both forced to retire next period (same age)
            d_plus = np.array([0])
        elif ad < 0 and t+1 == par.Tr-1:    # husband forced to retire next period (but not wife)
            d_plus = np.array([0,1])
        elif ad > 0 and t+1+ad == par.Tr-1: # wife forced to retire next period (but not husband)
            d_plus = np.array([0,2])
        else:                               # none are forced to retire next period
            d_plus = np.array([0,1,2,3])             
            
    return d_plus

@njit(parallel=True)
def couple_index(d,t,ad,par):
    """ finds the relevant couple index (used to look up in the single solution)

    Args:
        d (int): labor market status of household
        t (int): model time
        ad (int): age difference = age of wife - age of husband
        par (class): parameters
    
    Returns:
        sid_h,sid_w (tuple): 1 element is index for husband. 2 element is index for wife
    """
    # both retired
    if d == 0:
        sid_h = 0
        sid_w = 0

    # husband retired, wife working
    elif d == 1:
        if t+1+ad >= par.Tr-1:  # wife forced to retire next period
            sid_h = 0
            sid_w = 0
        else:
            sid_h = 0
            sid_w = 1

    # husband working, wife retired
    elif d == 2:
        if t+1 >= par.Tr-1:     # husband forced to retire next period
            sid_h = 0
            sid_w = 0
        else:
            sid_h = 1
            sid_w = 0

    # both working
    elif d == 3:
        if ad == 0 and t+1 >= par.Tr-1:     # both forced to retire next period (same age)
            sid_h = 0
            sid_w = 0
        elif ad < 0 and t+1 >= par.Tr-1:    # husband forced to retire next period (but not wife)
            sid_h = 0
            sid_w = 1
        elif ad > 0 and t+1+ad >= par.Tr-1: # wife forced to retire next period (but not husband)
            sid_h = 1
            sid_w = 0
        else:                               # none are forced to retire next period
            sid_h = 1
            sid_w = 1

    return sid_h,sid_w

@njit(parallel=True)
def state_translate(st,ind,par):
    """ translate the index st to the relevant state

    Args:
        st (int): index of state
        ind (str): should be 'elig' or 'high_skilled'
        par (class): contains information for the computation
    
    Returns:
        (int): 1 if ind is true 0 if false
    """
    # unpack
    states = par.states[st]
    
    # compute
    if ind == 'elig':
        if states[0] == 1:
            return 1
        else:
            return 0
    elif ind == 'high_skilled':
        if states[1] == 1:
            return 1
        else:
            return 0


##################################
####      pension system     #####
##################################
@njit(parallel=True)
def pension_look_up(t,male,st,erp,par):
    """ look up in the precomputed total pension payments for singles
    
    Args:
        t (int): time (in model)
        male (int): 0 if female and 1 if male
        st (int): index for state
        erp (int): index for retirement age
        par (class): contains information for computation

    Returns:
        pension_array (numpy.ndarray): total pension payment
    """
    return par.pension_arr[t,male,st,erp,:]

@njit(parallel=True)
def pension_look_up_c(t,male,ad,st,erp,par):
    """ look up in the precomputed total pension payments for couples
    
    Args:
        t (int): time (in model) - age of husband
        male (int): 0 if female and 1 if male
        st (int): index for state
        erp (int): index for retirement age
        par (class): contains information for computation

    Returns:
        (numpy.ndarray): total pension payment
    """
    ad_min = par.ad_min

    if male == 1:
        return par.pension_arr[t+ad_min,male,st,erp,:]
    elif male == 0:
        return par.pension_arr[t+ad+ad_min,male,st,erp,:]


#@njit(parallel=True)
def pension_precompute(par):
    """ precompute total pension payment
    
    Args:
        par (class): contains information for computation

    Returns:
        pension_array (numpy.ndarray): total pension payment
    """

    # states           
    T = par.T+par.ad_min+par.ad_max
    male = par.male
    num_st = len(par.states)
    erp = np.arange(3)  # same as [0,1,2]
    a = par.grid_a

    # initialize
    pension_arr = np.nan*np.zeros((T,len(male),num_st,len(erp),len(a)))
    
    # compute
    for t in range(T):
        for ma in male:
            for st in range(num_st):
                for e in erp:
                    pension_arr[t,ma,st,e,:] = pension(t,ma,st,e,a,par)

    # store
    par.pension_arr = pension_arr


@njit(parallel=True)
def pension(t,male,st,erp,a,par):
    """ compute total pension payment conditional on age, gender, states, retirement age (erp) and wealth (a)
    
    Args:
        t (int): time (in model)
        male (int): 0 if female and 1 if male
        st (int): index of state
        erp (int): index for retirement age
        a (numpy.ndarray): grid of wealth
        par (class): contains information for computation

    Returns:
        (numpy.ndarray): grid of total pension payment
    """

    # a. initialize
    pens = np.zeros(a.size)

    # b. oap
    if par.oap_age <= age(t,par) <= par.end_T:
        pens[:] = oap(t,par)
    
    # c. two year rule
    elif par.two_year <= age(t,par) < par.oap_age:

        if erp == 0:
            pens[:] = par.erp_high

        elif erp == 1:
            priv = priv_pension(t,male,st,a,par)
            pens[:] = np.maximum(0,166400 - 0.6*0.05*np.maximum(0,priv - 12600))

    # d. erp without two year
    elif par.erp_age <= age(t,par) < par.two_year:

        if erp == 1:
            priv = priv_pension(t,male,st,a,par)
            pens[:] = np.maximum(0,166400 - 0.6*0.05*np.maximum(0,priv - 12600))            
    
    # e. return (denominated in 100.000 DKR)
    return pens/100000    

@njit(parallel=True)
def oap(t,par): 
    """ old age pension (folkepension)"""
    return par.oap_base + par.oap_add 

@njit(parallel=True)
def priv_pension(t,male,st,a,par):
    """ compute private pension wealth conditional on age, gender, states and wealth (a)
    
    Args:
        t (int): time (in model)
        male (int): 0 if female and 1 if male
        st (int): index of state
        a (numpy.ndarray): grid of wealth
        par (class): contains information for computation

    Returns:
        priv (numpy.ndarray): grid of private pension wealth
    """

    # initialize
    priv = np.zeros(a.size)
    mask_a = np.where(a > par.tol)[0]

    # states     
    ag = age(t,par)
    hs = state_translate(st,'high_skilled',par)
    lw = np.log(a[mask_a]) # to avoid log of zero!
    #lw = np.log(a[mask_a]*100000) # to avoid log of zero!
    
    # compute
    if male == 1:    
        rpm = par.reg_pension_male      # regression coefficients for men    
        frac = rpm[0] + rpm[1]*ag + rpm[2]*(ag**2)/100 + rpm[3]*hs + rpm[4]*lw + rpm[5]*(lw**2) + rpm[6]*(lw**3)
    else:
       rpf = par.reg_pension_female     # regression coefficients for women 
       frac = rpf[0] + rpf[1]*ag + rpf[2]*(ag**2)/100 + rpf[3]*hs + rpf[4]*lw + rpf[5]*(lw**2) + rpf[6]*(lw**3)

    # final compute and return
    priv[mask_a] = 0.5*a[mask_a]#frac*a[mask_a]
    return priv    


##################################
####      income and tax     #####
##################################

@njit(parallel=True)
def labor_look_up(t,male,st,par):
    """ look up in the precomputed posttax labor (inclusive of shocks) income for singles 
    
    Args:
        t (int): time (in model)
        male (int): 0 if female and 1 if male
        st (int): index of state
        par (class): contains information

    Returns:
        (numpy.ndarray): posttax labor income with shocks
    """
    return par.labor[t,male,st,:]


@njit(parallel=True)
def labor_look_up_c(d,t,ad,st_h,st_w,par):
    """ look up in the precomputed posttax labor (inclusive of shocks) income for couples 

    Args:
        dummy (int): 0 if wife, 1 if husband and 2 if both are working
        ad_min (int): dummy used for look up in the solution 
        t (int): time (in model) - age of husband
        ad (int): age difference = age of husband - age of wife
        st_h (int): index of state for husband
        st_w (int): index of state for wife
        par_or_sim (class): either the par class (solving model) or the sim class (simulating the model)

    Returns:
        (numpy.ndarray): posttax labor income with shocks. If par_or_sim=par shocks are GH-nodes, if par_or_sim=sim shocks are random draws
    """  
    ad_min = par.ad_min
    if d == 1:      # only wife working
        return par.labor[t+ad+ad_min,0,st_w,:]
    elif d == 2:    # only husband working
        return par.labor[t+ad_min,1,st_h,:]
    elif d == 3:    # both are working
        return par.labor_c[t,ad+ad_min,st_h,st_w,:]
        

#@njit(parallel=True)
def labor_precompute(par):
    """ precompute posttax labor income (inclusive of shocks) across age, gender and states
    
    Args:
        par (class): contains information for computation

    Returns:
        labor (numpy.ndarray): posttax labor income for singles with shocks as GH-nodes
        labor_c (numpy.ndarray): posttax labor income for couples with shocks as GH-nodes        
    """
    
    # states
    ad_min = par.ad_min
    Tr = par.Tr+par.ad_min+par.ad_max     # Tr-1: only compute labor income up to forced retirement age
    male = par.male
    num_st = len(par.states)

    # shocks
    xi_men = par.xi_men
    xi_women = par.xi_women
    Nxi = par.Nxi    

    # initialize
    labor = np.zeros((Tr,len(male),num_st,Nxi))
    spouse_inc = 0.0
    
    # precompute individual labor income
    for t in range(Tr):
        for st in range(num_st):

            # men
            pre_h = labor_pretax(t,1,st,par)
            labor[t,1,st,:] = labor_posttax(t,pre_h,spouse_inc,par,xi_men)
            
            # women
            pre_w = labor_pretax(t,0,st,par)
            labor[t,0,st,:] = labor_posttax(t,pre_w,spouse_inc,par,xi_women) 

    # store
    par.labor = labor                          

    if par.couple:

        # states
        num_ad = len(par.age_dif)
        
        # shocks
        xi_men_corr = par.xi_men_corr
        xi_women_corr = par.xi_women_corr
        Nxi_corr = par.Nxi_men*par.Nxi_women   

        # initialize 
        labor_c = np.nan*np.zeros((Tr,num_ad,num_st,num_st,Nxi_corr))   

        # precompute joint labor income
        for t in range(par.Tr):   # here we don't need to extend bottom or top since we also look up over ad
            for ad in par.age_dif:
                for st_h in range(num_st):
                    for st_w in range(num_st):

                        # pretax
                        pre_h = labor_pretax(t,1,st_h,par)      # husband
                        pre_w = labor_pretax(t+ad,0,st_w,par)   # wife
                        
                        # posttax
                        labor_c[t,ad+ad_min,st_h,st_w,:] = (labor_posttax(t,pre_h,pre_w,par,xi_men_corr) + 
                                                            labor_posttax(t,pre_w,pre_h,par,xi_women_corr))

        # store
        par.labor_c = labor_c   

@njit(parallel=True)
def labor_posttax(t,inc_pre,spouse_inc,par,shock):
    """ compute posttax labor income including shocks to pretax labor income conditional on pretax income and income of the spouse
    
    Args:
        inc_pre (double): pretax labor income
        spouse_inc (double): pretax labor income for spouse
        par (class): contains information for computation
        shock (numpy.ndarray): shocks, can be either nodes for GH-integration or random draws for simulation

    Returns:
        (numpy.ndarray): posttax labor income including shocks to pretax labor income
    """    
    
    # pretax labor income multiplied with shock
    inc = inc_pre*shock
    
    # income definitions
    personal_income = (1 - par.tau_LMC)*inc
    if age(t,par) >= 65:
        taxable_income = personal_income - np.minimum(par.WD*inc,par.WD_upper) - par.fradrag
    else:
        taxable_income = personal_income - np.minimum(par.WD*inc,par.WD_upper)
    y_low_l = par.y_low + np.maximum(0,par.y_low-spouse_inc)

    # taxes
    T_c = np.maximum(0,par.tau_c*(taxable_income - y_low_l))
    T_h = np.maximum(0,par.tau_h*(taxable_income - y_low_l))
    T_l = np.maximum(0,par.tau_m*(personal_income - y_low_l))
    T_m = np.maximum(0,par.tau_m*(personal_income - par.y_low_m))
    T_u = np.maximum(0,np.minimum(par.tau_u,par.tau_max)*(personal_income - par.y_low_u))
    
    # return posttax labor income
    return personal_income - T_c - T_h - T_l - T_m - T_u    

@njit(parallel=True)
def labor_pretax(t,male,st,par):
    """ compute pretax labor income conditional on age, gender and states
    
    Args:
        t (int): time (in model)
        male (int): 0 if female and 1 if male
        st (int): index for state
        par (class): contains information for computation

    Returns:
        (double): pretax labor income (absolute amount)
    """

    # states
    ag = age(t,par)
    hs = state_translate(st,'high_skilled',par) # 1 if agent is high_skilled

    # compute
    if male == 1:
        rlm = par.reg_labor_male    # regression coefficients for men
        log_inc = rlm[0] + rlm[1]*hs + rlm[2]*ag + rlm[3]*(ag**2)/100
    elif male == 0:
        rlf = par.reg_labor_female  # regression coefficients for women
        log_inc = rlf[0] + rlf[1]*hs + rlf[2]*ag + rlf[3]*(ag**2)/100
    
    # exponentiate and denominate in 100.000 dkr
    return np.exp(log_inc)/100000


##################################
####         survival        #####
##################################
@njit(parallel=True)
def survival_look_up(t,male,par):
    """ look up in the precomputed survival probabilities for singles
    
    Args:
        t (int): time (in model)
        male (int): 0 if female and 1 if male
        par (class): contains information

    Returns:
        (double): survival probability
    """
    return par.survival_arr[t,male]

@njit(parallel=True)
def survival_look_up_c(t,ad,par):
    """ look up in the precomputed survival probabilities for couples
    
    Args:
        t (int): time (in model) - age of husband
        ad (int): age difference = age of husband - age of wife
        par (class): contains information

    Returns:
        (tuple): survival probability for women and men (in that order)
    """
    ad_min = par.ad_min
    return par.survival_arr[t+ad+ad_min,0],par.survival_arr[t+ad_min,1]   # women first    

#@njit(parallel=True)
def survival_precompute(par):
    """ precomputes survival probabilities across time and gender

    Args:
        par (class): contains information for the computation
    
    Returns:
        survival_arr (numpy.ndarray): store array with survival probabilities in par class
    """
    
    # unpack    
    T = par.T+par.ad_min+par.ad_max
    male = par.male
    
    # initialize
    survival_arr = np.nan*np.zeros((T,2))
    
    # compute
    for t in range(T):
        for ma in male:
            survival_arr[t,ma] = survival(t,ma,par)

    # store      
    par.survival_arr = survival_arr

@njit(parallel=True)
def survival(t,male,par):
    """ compute survival probability conditional on age and gender
    
    Args:
        t (int): time (in model)
        male (int): 0 if female and 1 if male
        par (class): contains information for the computation
    
    Returns:
        (double): survival probability (between zero and one)
    """    

    # age
    ag = age(t,par)

    if ag >= 110:   # dead
        return 0.0
    
    else:
        if male == 1: 
            rsm = par.reg_survival_male
            deadP = min(1,np.exp(rsm[0] + rsm[1]*ag))
        elif male == 0:       
            rsf = par.reg_survival_female
            deadP = min(1,np.exp(rsf[0] + rsf[1]*ag))
        return min(1,(1 - deadP)) 