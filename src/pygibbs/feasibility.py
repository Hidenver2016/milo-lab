import pylab
import cvxopt
import cvxopt.solvers
import csv, sys, os
try:
    import cplex
    IsCplexInstalled = True
except ImportError:
    IsCplexInstalled = False
    
R = 8.31e-3 # gas constant (kJ/K mol)
T = 300 # temperature (K)

class LinProgNoSolutionException(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
def linprog(f, A, b, lb=[], ub=[], log_stream=None):
    """
        The constraints are:
            A*x <= b
            lb <= x <= ub
        
        The optimization rule is:
            minimize f*x
        
        In matrix A:
            rows are reactions (indexed by 'r') - total of Nr
            columns are compounds (indexed by 'c') - total of Nc
        
        All other parameters (f, b, lb, ub) should be column vectors, with the following sizes:
            f  - Nc x 1
            b  - Nr x 1
            lb - list of pairs (column_index, lower_bound)
            ub - list of pairs (column_index, upper_bound)
    """
    (Nr, Nc) = A.shape
    if (f.shape[0] != Nc or f.shape[1] != 1):
        raise Exception("linprog: 'f' must be a column vector whose length matches the number of columns in 'A'")
    if (b.shape[0] != Nr or b.shape[1] != 1):
        raise Exception("linprog: 'b' must be a column vector whose length matches the number of rows in 'A'")
    
    if True: # currently CPLEX does not work (claims every problem is infeasible)
        for (c, bound) in lb:
            row_lower = pylab.zeros(Nc)
            row_lower[c] = -1
            A = pylab.vstack([A, row_lower])
            b = pylab.vstack([b, [-bound]])
        for (c, bound) in ub:
            row_upper = pylab.zeros(Nc)
            row_upper[c] = 1
            A = pylab.vstack([A, row_upper])
            b = pylab.vstack([b, [bound]])
        
        # make sure the values are floating point (not integer)
        # and convert the matrices to cvxopt format
        c = cvxopt.matrix(f * 1.0)
        G = cvxopt.matrix(A * 1.0)
        h = cvxopt.matrix(b * 1.0)
        cvxopt.solvers.options['show_progress'] = False
        cvxopt.solvers.options['LPX_K_MSGLEV'] = 0
        sol = cvxopt.solvers.lp(c, G, h, solver='glpk')
        if (not sol['x']):
            return None
        else:
            return pylab.matrix(sol['x'])
    else:
        cpl = cplex.Cplex()
        if (log_stream != None):
            cpl.set_log_stream(log_stream)
        else:
            cpl.set_log_stream(None)
        cpl.set_results_stream(None)
        #cpl.set_warning_stream(None)
        
        cpl.set_problem_name('LP')
        cpl.variables.add(names=["c%d" % c for c in range(Nc)])
        cpl.variables.set_lower_bounds(lb)
        cpl.variables.set_upper_bounds(ub)
    
        cpl.objective.set_linear([(c, f[c, 0]) for c in range(Nc)])
        
        for r in range(Nr):
            cpl.linear_constraints.add(senses='L', names=["r%d" % r])
            for c in range(Nc):
                cpl.linear_constraints.set_coefficients(r, c, A[r, c])
        cpl.linear_constraints.set_rhs([(r, b[r, 0]) for r in range(Nr)])
        cpl.write("../res/test.lp", "lp")
        cpl.solve()
        if (cpl.solution.get_status() != cplex.callbacks.SolveCallback.status.optimal):
            return None
        else:
            return pylab.matrix(cpl.solution.get_values()).T

def find_feasible_concentrations(S, dG0_f, c_range=(1e-6, 1e-2), bounds=None, log_stream=None):
    """ 
        Find a distribution of concentration that will satisfy the 'relaxed' thermodynamic constraints.
        The 'relaxation' means that there is a slack variable 'B' where all dG_r are constrained to be < B.
        Note that B can also be negative, which will happen when the pathway is feasible.
    """
    (Nr, Nc) = S.shape
    (c_min, c_max) = c_range
    
    # compute right hand-side vector - r,
    # i.e. the deltaG0' of the reactions divided by -RT
    if (S.shape[1] != dG0_f.shape[0]):
        raise Exception("The S matrix has %d columns, while the dG0_f vector has %d" % (S.shape[1], dG0_f.shape[0]))
    
    # matrix for linear programming computation
    A = pylab.hstack([S, -1 * pylab.ones((Nr, 1))]) # add another column to S for the slack variable 'B'
    
    good_indices = pylab.find(pylab.isfinite(dG0_f))
    b = pylab.dot(S[:, good_indices], dG0_f[good_indices, :]) / (-R * T)
    [A_margin, b_margin] = generate_constraints_opt(dG0_f, c_min, c_max, bounds)
    if (A_margin != []):
        A = pylab.vstack([A, A_margin])
        b = pylab.vstack([b, b_margin])
    
    # function for minimization (x'*f) = [0, .. 0, B]
    f = pylab.matrix(pylab.hstack([0] * Nc + [1])).T
    lb = [(Nc, -1e6)]
    ub = [(Nc, 1e6)]
    
    # solve using linprog command (find x such that S*x <= b)
    x = linprog(f, A, b, lb, ub, log_stream)
    if (x == None):
        raise LinProgNoSolutionException("")
    
    dG_f = pylab.zeros((Nc, 1))
    nan_indices = pylab.find(pylab.isnan(dG0_f))
    dG_f[good_indices, :] = dG0_f[good_indices, :] + R * T * x[good_indices, :]
    dG_f[nan_indices, :] = R * T * x[nan_indices, :]

    concentrations = pylab.exp(x[:Nc, 0])
    concentrations[nan_indices] = pylab.sqrt(c_max * c_min) # use the geometric average for unknown concentrations
    B = x[Nc, 0] * R * T # convert to units of kJ/mol

    return (dG_f, concentrations, B)

def find_pCr(S, dG0_f, c_mid=1e-3, ratio=3.0, bounds=None, log_stream=None):
    """ 
        Compute the feasibility of a given set of reactions
    
        input: s1 = stoichiometric matrix (reactions x compounds)
               dG = deltaG0'-formation values for all compounds (in kJ/mol) (1 x compounds)
               c_mid = the default concentration
               ratio = the ratio between the distance of the upper bound from c_mid and the lower bound from c_mid (in logarithmic scale)
        
        output: (concentrations, margin)
    """
    (Nr, Nc) = S.shape
    
    # compute right hand-side vector - r,
    # i.e. the deltaG0' of the reactions divided by -RT
    if (S.shape[1] != dG0_f.shape[0]):
        raise Exception("The S matrix has %d columns, while the dG0_f vector has %d" % (S.shape[1], dG0_f.shape[0]))
    
    # matrix for linear programming computation
    A = pylab.hstack([S, pylab.zeros((Nr, 1))]) # add to columns to S1 (for M- and M+)
    
    good_indices = pylab.find(pylab.isfinite(dG0_f))
    b = pylab.dot(S[:, good_indices], dG0_f[good_indices, :]) / (-R * T)
    [A_margin, b_margin] = generate_constraints_pCr(dG0_f, c_mid, ratio, bounds)
    if (A_margin != []):
        A = pylab.vstack([A, A_margin])
        b = pylab.vstack([b, b_margin])
    
    # function for minimization (x'*f) - [0, .. 0, pCr]
    f = pylab.matrix(pylab.hstack([0] * Nc + [1])).T
    lb = [(Nc, 0)]
    ub = [(Nc, 1e6)]
    
    # solve using linprog command (find x such that S*x <= b)
    x = linprog(f, A, b, lb, ub, log_stream)
    if (x == None):
        raise LinProgNoSolutionException("")
    
    dG_f = pylab.zeros((Nc, 1))
    nan_indices = pylab.find(pylab.isnan(dG0_f))
    dG_f[good_indices, :] = dG0_f[good_indices, :] + R * T * x[good_indices, :]
    dG_f[nan_indices, :] = R * T * x[nan_indices, :]

    concentrations = pylab.exp(x[:Nc, 0])
    concentrations[nan_indices] = c_mid
    pCr = x[Nc, 0] / pylab.log(10) # move from the natural base to base 10

    return (dG_f, concentrations, pCr)

def find_unfeasible_concentrations(S, dG0_f, c_range, c_mid=1e-4, bounds=None, log_stream=None):
    """ 
        Almost the same as find_pCr, but adds a global restriction on the concentrations (for compounds
        that don't have specific bounds in 'bounds').
        After the solution which optimizes the pCr is found, any concentration which does not confer
        to the limits of c_range will be truncated to the closes allowed concentration.
        If at least one concentration needs to be adjusted, then pCr looses its meaning
        and therefore is returned with the value None.
    """
    (Nr, Nc) = S.shape
    (dG_f, concentrations, pCr) = find_pCr(S, dG0_f, c_mid, bounds, log_stream)

    for c in xrange(Nc):
        if (pylab.isnan(dG0_f[c, 0])):
            continue # unknown dG0_f - therefore the concentration of this compounds is meaningless

        if ((bounds == None or bounds[c][0] == None) and concentrations[c, 0] < c_range[0]):
            concentrations[c, 0] = c_range[0]
            dG_f[c, 0] = dG0_f[c, 0] + R * T * c_range[0]
            pCr = None
        elif ((bounds == None or bounds[c][1] == None) and concentrations[c, 0] > c_range[1]):
            concentrations[c, 0] = c_range[1]
            dG_f[c, 0] = dG0_f[c, 0] + R * T * c_range[1]
            pCr = None

    return (dG_f, concentrations, pCr)

def generate_constraints_opt(dG0_f, c_min=1e-6, c_max=1e-2, bounds=None):   
    """
        For any compound that does not have an explicit bound set by the 'bounds' argument,
        create a bound using the 'margin' variables (the last to columns of A).
    """
    
    Nc = dG0_f.shape[0]
    A = []
    b = []

    if (bounds != None and len(bounds) != Nc):
        raise Exception("The concentration bounds list must be the same length as the number of compounds")
    
    for c in xrange(Nc):
        if (pylab.isnan(dG0_f[c, 0])):
            continue # unknown dG0_f - cannot bound this compound's concentration at all

        # add 2 rows for each substance:
        row_lower = pylab.zeros(Nc + 1)
        row_lower[c] = -1
        if (bounds == None or bounds[c][0] == None):
            # lower bound: -x_i <= -ln(Cmin)
            b.append(-pylab.log(c_min))
        else:
            # this compound has a specific lower bound on its activity
            b.append(-pylab.log(bounds[c][0]))
        A.append(row_lower)

        row_upper = pylab.zeros(Nc + 1)
        row_upper[c] = 1
        if (bounds == None or bounds[c][1] == None):
            # upper bound: x_i <= ln(Cmax)
            b.append(pylab.log(c_max))
        else:
            # this compound has a specific upper bound on its activity
            b.append(pylab.log(bounds[c][1]))
        A.append(row_upper)
        
    return (pylab.matrix(A), pylab.matrix(b).T)

def generate_constraints_pCr(dG0_f, c_mid, ratio, bounds=None):   
    """
        For any compound that does not have an explicit bound set by the 'bounds' argument,
        create a bound using the 'margin' variables (the last to columns of A).
        
        The constraints will eventually look like this:
        
        ln(c_mid) - r/(1+r) * pC <= ln(c) <= ln(c_mid) + 1/(1+r) * pC 
    """
    
    Nc = dG0_f.shape[0]
    A = []
    b = []

    if (bounds != None and len(bounds) != Nc):
        raise Exception("The concentration bounds list must be the same length as the number of compounds")
    
    for c in xrange(Nc):
        if (pylab.isnan(dG0_f[c, 0])):
            continue # unknown dG0_f - cannot bound this compound's concentration at all

        # add 2 rows for each substance:
        row_lower = pylab.zeros(Nc + 1)
        row_lower[c] = -1
        if (bounds == None or bounds[c][0] == None):
            # lower bound: -x_i - r*(1+r) * pC <= -ln(Cmid)
            row_lower[-1] = -ratio / (ratio + 1.0)
            b.append(-pylab.log(c_mid))
        else:
            # this compound has a specific lower bound on its activity
            b.append(-pylab.log(bounds[c][0]))
        A.append(row_lower)

        row_upper = pylab.zeros(Nc + 1)
        row_upper[c] = 1
        if (bounds == None or bounds[c][1] == None):
            # upper bound: x_i - 1/(1+r) * pC <= ln(Cmid)
            row_upper[-1] = -1.0 / (ratio + 1.0)
            b.append(pylab.log(c_mid))
        else:
            # this compound has a specific upper bound on its activity
            b.append(pylab.log(bounds[c][1]))
        A.append(row_upper)
        
    return (pylab.matrix(A), pylab.matrix(b).T)

if (__name__ == "__main__"):
    from groups import GroupContribution, GroupMissingTrainDataError, GroupDecompositionError
    from kegg import KeggParseException, KeggMissingModuleException
    
    gc = GroupContribution(sqlite_name="gibbs.sqlite", html_name="dG0_test")
    gc.init()
    c_min = 1e-6
    c_mid = 1e-4
    c_max = 1e-2
    pH = 8
    I = 0.1
    T = 300
    map_cid = {201:2, 454:8} # CIDs that should be mapped to other CIDs because they are unspecific (like NTP => ATP)
    
    f = open("../res/feasibility.csv", "w")
    csv_output = csv.writer(f)
    csv_output.writerow(("MID", "module name", "pH", "I", "T", "pCr"))
    for mid in sorted(gc.kegg().mid2rid_map.keys()):
    #for mid in [9]:
        module_name = gc.kegg().mid2name_map[mid]
        try:
            for pH in [6, 7, 8, 9]:
                for I in [0.0, 0.1, 0.2]:
                    (S, rids, fluxes, cids) = gc.kegg().get_module(mid)
                    (Nr, Nc) = S.shape
                    dG0_f = pylab.zeros((Nc, 1))
                    bounds = []
                    for c in range(Nc):
                        cid = map_cid.get(cids[c], cids[c])
                        try:
                            pmap = gc.estimate_pmap_keggcid(cid)
                            dG0_f[c] = gc.pmap_to_dG0(pmap, pH, I, T)
                        except KeggParseException:
                            sys.stderr.write("M%05d: Unknown compound in module (C%05d), using NaN\n" % (mid, cid))
                            dG0_f[c] = pylab.nan
                        except GroupMissingTrainDataError:
                            sys.stderr.write("M%05d: A compound with a unique group exists in module (C%05d), using NaN\n" % (mid, cid))
                            dG0_f[c] = pylab.nan
                        except GroupDecompositionError:
                            sys.stderr.write("M%05d: Cannot decompose a compound in module (C%05d), using NaN\n" % (mid, cid))
                            dG0_f[c] = pylab.nan
                
                    bounds = [gc.kegg().cid2bounds.get(cid, (None, None)) for cid in cids]

                    try:
                        (dG_f, concentrations, pCr) = find_pCr(S, dG0_f, c_mid=c_mid, bounds=bounds)
                        dG_r = pylab.dot(S, dG_f)
                        
                        sys.stderr.write("M%05d: pH = %g, I = %g, pCr = %.2f\n" % (mid, pH, I, pCr))
                        csv_output.writerow([mid, module_name, pH, I, T, pCr])
                    except LinProgNoSolutionException:
                        sys.stderr.write("M%05d: Pathway is theoretically infeasible\n" % mid)

                    try:
                        (dG_f, concentrations, B) = find_feasible_concentrations(S, dG0_f, c_min=c_min, c_max=c_max, bounds=bounds)
                        dG_r = pylab.dot(S, dG_f)
                        
                        sys.stderr.write("M%05d: pH = %g, I = %g, B = %.2f\n" % (mid, pH, I, B))
                        csv_output.writerow([mid, module_name, pH, I, T, B])
                    except LinProgNoSolutionException:
                        sys.stderr.write("M%05d: Pathway is theoretically infeasible\n" % mid)
                        
        except KeggMissingModuleException:
            continue
    f.close()