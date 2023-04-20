import numpy as np
import do_mpc
from casadi import *
import math
import matplotlib.pyplot as plt
import matplotlib as mpl


m = .5  # drone_mass
g = 9.81
arm_length = 1
Ixx = 1.2
Iyy = 1.1
Izz = 1.0


model_type = "discrete"
mpc_model = do_mpc.model.Model(model_type)
mpc_controller = None
estimator = None
u = None
x = None

pos = mpc_model.set_variable('states',  'pos', (3, 1))
theta = mpc_model.set_variable('states',  'theta', (3, 1))

dpos = mpc_model.set_variable('states',  'dpos', (3, 1))
dtheta = mpc_model.set_variable('states',  'dtheta', (3, 1))

u_th = mpc_model.set_variable('inputs',  'u_th', (4, 1))
u_ti = mpc_model.set_variable('inputs',  'u_ti', (4, 1))


ddpos = mpc_model.set_variable('algebraic',  'ddpos', (3, 1))
ddtheta = mpc_model.set_variable('algebraic',  'ddtheta', (3, 1))
last_state = mpc_model.set_variable(var_type='_tvp', var_name='last_state',shape=(12, 1))
last_input = mpc_model.set_variable(var_type='_tvp', var_name='last_input',shape=(8, 1))
drone_acc = mpc_model.set_variable(var_type='_tvp', var_name='drone_acc',shape=(6, 1))






mpc_model.set_rhs('pos', dpos)
mpc_model.set_rhs('theta', dtheta)
mpc_model.set_rhs('dpos', ddpos)
mpc_model.set_rhs('dtheta', ddtheta)

T1 = last_input[0]
T2 = last_input[1]
T3 = last_input[2]
T4 = last_input[3]
theta1 = last_input[4]
theta2 = last_input[5]
theta3 = last_input[6]
theta4 = last_input[7]

x = last_state[0]
y = last_state[1]
z = last_state[2]
roll = last_state[3]
pitch = last_state[4]
yaw = last_state[5]

dx = last_state[6]
dy = last_state[7]
dz = last_state[8]
droll = last_state[9]
dpitch = last_state[10]
dyaw = last_state[11]

ddx = ddpos[0]
ddy = ddpos[1]
ddz = ddpos[2]
ddroll = ddtheta[0]
ddpitch = ddtheta[1]
ddyaw = ddtheta[2]

f = vertcat(
    dx,
    dy,
    dz,
    droll,
    dpitch,
    dyaw,

    (T2*sin(theta2) - T4*sin(theta4) - m*g*sin(pitch))/m,
    # 2
    (T1*sin(theta1) - T3*sin(theta3) - m*g*sin(roll))/m,
    # 3
    (T1*cos(theta1) + T2*cos(theta2) + T3*cos(theta3) + T4*cos(theta4) - m*g*cos(roll)*cos(pitch))/m,
    # 4
    ((T2*cos(theta2)*arm_length) - (T4*cos(theta4)*arm_length) + (Iyy*dpitch*dy + Izz*dpitch*dy))/Ixx,
    # 5
    (T1*cos(theta1)*arm_length - T3*cos(theta3)*arm_length + (-Ixx*droll*dy + Izz*droll*dy))/Iyy,
    # 6
    (T1*sin(theta1)*arm_length + T2*sin(theta2)*arm_length + T3*sin(theta3)*arm_length + T4*sin(theta4)*arm_length + (Ixx*droll*dpitch - Iyy*droll*dpitch))/Izz
)




u_vec = vertcat(
    u_th,
    u_ti
)
state_vec = vertcat(
    pos,
    theta,
    dpos,
    dtheta,
)

A = jacobian(f, last_state)
print((A.shape))
B = jacobian(f, last_input)
print((B.shape))

result_vec = vertcat(
    ddx,
    ddy,
    ddz,
    ddroll,
    ddpitch,
    ddyaw,
)
euler_lagrange = (result_vec-drone_acc) - (A@(state_vec-last_state))[6:] - (B@(u_vec-last_input))[6:]

#print(euler_lagrange)

target_point = np.array([[0.0],[0.0],[1.0]])
mpc_model.set_alg('euler_lagrange', euler_lagrange)
mpc_model.set_expression(expr_name='cost', expr=sum1(.9*sqrt((pos[0]-target_point[0])**2 + (pos[1]-target_point[1])**2 + (pos[2]-target_point[2])**2) +.0000000001*sqrt((u_th[0])**2 + (u_th[1])**2 + (u_th[2])**2 + (u_th[3])**2) ))
mpc_model.set_expression(expr_name='mterm', expr=sum1(.9*sqrt((pos[0]-target_point[0])**2 + (pos[1]-target_point[1])**2 + (pos[2]-target_point[2])**2)))

mpc_model.setup()


mpc_controller = do_mpc.controller.MPC(mpc_model)


setup_mpc = {
    'n_horizon': 7,
    'n_robust': 1,
    'open_loop': 0,
    't_step': 0.001,
    'state_discretization': 'collocation',
    'collocation_type': 'radau',
    'collocation_deg': 3,
    'collocation_ni': 1,
    'store_full_solution': True,
    # Use MA27 linear solver in ipopt for faster calculations:
    'nlpsol_opts': {'ipopt.linear_solver': 'mumps', 'ipopt.print_level':0, 'ipopt.sb': 'yes', 'print_time':0}
}

mpc_controller.set_param(**setup_mpc)
tvp_template = mpc_controller.get_tvp_template()
n_horizon = 7
def tvp_fun(t_now):
    for k in range(n_horizon+1):
        tvp_template['_tvp',k, 'last_state'] = [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]
        tvp_template['_tvp',k, 'last_input'] = [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]
        tvp_template['_tvp',k, 'drone_acc'] = [0.0,0.0,0.0,0.0,0.0,0.0]
        return tvp_template
mpc_controller.set_tvp_fun(tvp_fun)


mterm = mpc_model.aux['mterm']
lterm = mpc_model.aux['cost']

mpc_controller.set_objective(mterm=mterm, lterm=lterm)
# Input force is implicitly restricted through the objective.
mpc_controller.set_rterm(u_th=1e-4)
mpc_controller.set_rterm(u_ti=1e-3)

tilt_limit = pi/2
thrust_limit = 50
u_upper_limits = np.array([thrust_limit, thrust_limit, thrust_limit, thrust_limit])
u_lower_limits =  np.array([0, 0, 0, 0])
u_ti_upper_limits = np.array([tilt_limit, tilt_limit, tilt_limit, tilt_limit])
u_ti_lower_limits =  np.array([-tilt_limit, -tilt_limit, -tilt_limit, -tilt_limit])

x_limits = np.array([inf, inf, inf, pi/2, pi/2, pi/2, .1, .1, .1, 1, 1, 1])

mpc_controller.bounds['lower','_u','u_th'] = u_lower_limits
mpc_controller.bounds['upper','_u','u_th'] = u_upper_limits
mpc_controller.bounds['lower','_u','u_ti'] = u_ti_lower_limits
mpc_controller.bounds['upper','_u','u_ti'] = u_ti_upper_limits

mpc_controller.bounds['lower','_x','pos'] = -x_limits[0:3]
mpc_controller.bounds['upper','_x','pos'] = x_limits[0:3]

mpc_controller.bounds['lower','_x','theta'] = -x_limits[3:6]
mpc_controller.bounds['upper','_x','theta'] = x_limits[3:6]

mpc_controller.bounds['lower','_x','dpos'] = -x_limits[6:9]
mpc_controller.bounds['upper','_x','dpos'] = x_limits[6:9]

mpc_controller.bounds['lower','_x','dtheta'] = -x_limits[9:12]
mpc_controller.bounds['upper','_x','dtheta'] = x_limits[9:12]


mpc_controller.setup()
x0 = np.array([0.0,0.0,0.0,0.0,0.0,0.0,.0,0.0,0.0,0.0,0.0,0.0])
mpc_controller.x0 = x0
mpc_controller.set_initial_guess()



u_val = [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]

estimator = do_mpc.estimator.StateFeedback(mpc_model)
simulator = do_mpc.simulator.Simulator(mpc_model)
params_simulator = {
    # Note: cvode doesn't support DAE systems.
    'integration_tool': 'idas',
    'abstol': 1e-10,
    'reltol': 1e-10,
    't_step': 0.001
}

simulator.set_param(**params_simulator)
tvp_template2 = simulator.get_tvp_template()
n_horizon = 7
def tvp_fun2(t_now):
    tvp_template2['last_state'] = [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]
    tvp_template2['last_input'] = [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]
    tvp_template2['drone_acc'] = [0.0,0.0,0.0,0.0,0.0,0.0]
    return tvp_template2
simulator.set_tvp_fun(tvp_fun2)
simulator.setup()
estimator.x0 = x0

mpl.rcParams['font.size'] = 18
mpl.rcParams['lines.linewidth'] = 3
mpl.rcParams['axes.grid'] = True

mpc_graphics = do_mpc.graphics.Graphics(mpc_controller.data)
sim_graphics = do_mpc.graphics.Graphics(simulator.data)

fig, ax = plt.subplots(2, sharex=True, figsize=(16,9))
fig.align_ylabels()

for g in [sim_graphics, mpc_graphics]:
    # Plot the positions
    g.add_line(var_type='_x', var_name='pos', axis=ax[0])
    #g.add_line(var_type='_x', var_name='theta', axis=ax[0])
    #g.add_line(var_type='_x', var_name='z', axis=ax[2])

    # Plot the thrusts
    g.add_line(var_type='_u', var_name='u_th', axis=ax[1])
    #g.add_line(var_type='_u', var_name='T2', axis=ax[4])
    #g.add_line(var_type='_u', var_name='T3', axis=ax[5])
    #g.add_line(var_type='_u', var_name='T4', axis=ax[6])



ax[0].set_ylabel('pos')
#ax[1].set_ylabel('theta')
ax[1].set_ylabel('thrusts')
ax[1].set_xlabel('time (s)')





#u0 = mpc_controller.make_step(x0)



simulator.reset_history()
simulator.x0 = x0
mpc_controller.reset_history()

for i in range(2000):
    u0 = mpc_controller.make_step(x0)
    x0 = simulator.make_step(u0)
    tvp_template = mpc_controller.get_tvp_template()
    n_horizon = 7
    def tvp_fun(t_now):
        for k in range(n_horizon+1):
            tvp_template['_tvp',k,'last_state'] = x0
            tvp_template['_tvp',k,'last_input'] = u0
            tvp_template['_tvp',k,'drone_acc'] = [0.0,0.0,0.0,0.0,0.0,0.0]
            return tvp_template
    mpc_controller.set_tvp_fun(tvp_fun)

    tvp_template2 = simulator.get_tvp_template()
    def tvp_fun2(t_now):
        tvp_template2['last_state'] = x0
        tvp_template2['last_input'] = u0
        tvp_template2['drone_acc'] = [0.0,0.0,0.0,0.0,0.0,0.0]
        return tvp_template2
  
    simulator.set_tvp_fun(tvp_fun2)
    print(u0)
    print(x0)

mpc_graphics.plot_predictions(t_ind=0)
# Plot results until current time
sim_graphics.plot_results()
sim_graphics.reset_axes()#
fig
    




