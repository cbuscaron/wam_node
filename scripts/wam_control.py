#!/usr/bin/env python

import numpy as np
import time
import rospy
import roslib;

from wam_common.msg import RTJointPos
from wam_common.srv import *
from numpy import zeros
from std_srvs.srv import Empty
from sensor_msgs.msg import JointState


def get_wam_joint_coordinates():

    msg = rospy.wait_for_message('/wam/joint_states', JointState)
    return list(msg.position)


def set_wam_joint_hold(hold):
    """Turn on/off the joint lock so you can manipulate the WAM by hand.
    args:
      hold: True if you want the WAM to maintain its joint pose. False
        if you want to be able to move it by hand.
    """
    msg = HoldRequest()
    msg.hold = hold
    wam_hold_service = rospy.ServiceProxy('/wam/hold_joint_pos', Hold)
    try:
        resp1 = wam_hold_service(msg)
    except rospy.ServiceException as exc:
        print("Service did not process request: " + str(exc))


def create_joint_trajectory(start_position, end_position,
                             duration_of_trajectory, frequency_of_trajectory):
    """
    Create a trajectory from start_position to end_position.

    The trajectory is the linear interpolation from start to end. It will last
    duration_of_trajectory seconds.  Be careful that you pick your start/end
    points such that the hand doesn't turn into the arm.

    args:
      start_position: a 7 element list containing the start position for each
        joint.
      end_position: a 7 element list containing the end position for each
        joint.
      duration: a float containing the time the trajectory should finish at
        in seconds.
      frequency_of_trajectory: the frequency of the trajectory you want to
        generate in Hz.

    returns:
      trajectory: an N * 7 numpy array of joint coordinates.
      vel_lims: the joint velocities required to perform trajectory.
        v1 = abs((p2 - p1) * 250). The last velocity, vn, is set equal to v(n-1)
        The absolute value is required for the WAM. Even if it's traveling in
        the negative direction, a positive value should be used.
    """

    frequency_of_ros_messages = frequency_of_trajectory # in Hz.
    number_of_way_points = duration_of_trajectory * frequency_of_ros_messages
    number_of_joints = start_position.__len__()
    trajectory = np.zeros((number_of_joints, number_of_way_points))

    for i in xrange(number_of_joints):
        trajectory[i] = np.linspace(start_position[i], end_position[i],
                                    number_of_way_points)
    trajectory = trajectory.T.copy()
    vel_lims = np.diff(trajectory, axis=0)
    #Because this is discrete differentiation,
    # the last value is missing: len(vel_lims) = len(trajectory) - 1
    # so we just repeat the last calculated velocity.
    vel_lims = np.append(vel_lims, [[x for x in vel_lims[-1,:]]], axis = 0)
    vel_lims = vel_lims * frequency_of_trajectory
    vel_lims = np.absolute(vel_lims)

    if vel_lims.all() > 1.0:
        raise ValueError("One or more of the values in the specified velocities"
                         "Exceed 1 rad / second. The robot won't like this."
                         "Adjust the trajectory so that each point can be "
                         "reached without exceeding this limit.")
    return trajectory, vel_lims


def send_joint_trajectory(trajectory, velocities, frequency=250):
    """
    This is used to send a trajectory to the WAM arm at a given frequency.

    args:
      trajectory: a Nx7 numpy array. The 7 columns correspond to the 7 joints
        on a WAM.
      velocities: a Nx7 numpy array. The 7 columns correspond to the 7 joints
        on a WAM. Should all be positive (even if traveling in the negative
        direction.
      frequency: The frequency the trajectory should be published at.

    returns:
      None.
    """
    pub = rospy.Publisher("/wam/jnt_pos_cmd", RTJointPos, queue_size=10)
    #If wam_node is running, it will be connected to this publisher.
    #Mostly this loop is here because you want to make sure the publisher
    #gets set up before it starts sending information.
    while pub.get_num_connections() < 1:
        print "Waiting on the publisher to go up."
        rospy.sleep(0.5)

    trajectory_length = trajectory.__len__()
    finished = False
    traj_row = 0
    message_for_service = RTJointPos()

    r = rospy.Rate(frequency)

    while not rospy.is_shutdown() and not finished:
        message_for_service.joints = trajectory[traj_row]
        message_for_service.rate_limits = velocities[traj_row]
        traj_row += 1
        pub.publish(message_for_service)
        if traj_row == trajectory_length - 1:
            finished = True
        r.sleep()

def create_and_send_wam_trajectory(wam_start, wam_end, duration, frequency=250):
    """ Create and send a trajectory that's a linear interpolation between
    wam_start and wam_end that lasts duration seconds send at frequency.

    args:
      wam_start: a 1x7 array of joint coordinates.
      wam_end: a 1x7 array of joint coordinates.
      duration: A float. The duration of the trajectory in seconds.
      frequency: The frequency of values. With the default, a new position is
        specified for every 0.004 seconds. 250 Hz is what wam_node is expecting.

    returns:
      None
      """

    joint_traj, joint_vels = create_joint_trajectory(wam_start, wam_end,
                                                     duration, frequency)
    send_joint_trajectory(joint_traj, joint_vels, frequency)


def move_wam_from_current_location(wam_end, duration, frequency=250):
    """ Create and send a trajectory that's a linear interpolation between
    where the wam currently is and wam_end that lasts duration seconds.
    Publishes the trajectory at frequency Hz.

    args:
      wam_end: a 1x7 array of joint coordinates.
      duration: A float. The duration of the trajectory in seconds.
      frequency: The frequency of values. With the default, a new position is
        specified for every 0.004 seconds. 250 Hz is what wam_node is expecting.

    returns:
      None
      """
    wam_start = get_wam_joint_coordinates()
    joint_traj, joint_vels = create_joint_trajectory(wam_start, wam_end,
                                                    duration, frequency)
    send_joint_trajectory(joint_traj, joint_vels, frequency)


def  request_wam_move(end_point, velocity_limits):
    """
    Uses a service call to have the WAM move to the end point. Goes at its own
    pace.

    args:
      end_point: a 7 long list of joint coordinates.
      velocity_limits: a 7 long list of joint velocity limits.
    """

    move_wam_srv = rospy.ServiceProxy('/wam/joint_move', JointMove)
    try:
        resp1 = move_wam_srv(end_point)
    except rospy.ServiceException as exc:
        print("Service did not process request: " + str(exc))

if __name__ == "__main__":
    nody = rospy.init_node("wam_motion_control")


    wam_home = [0.0, -2.0, 0.0, 5.0]
    ##move_wam_from_current_location(wam_home, 2, 250)
    hit_pont = [0.0, -1.4, 0.0, 5.83]

    move_wam_from_current_location(hit_pont, 1.0, 250)
    time.sleep(1.0)
    move_wam_from_current_location(wam_home, 2, 250)



    '''
    move_wam_from_current_location(wam_home, 2, 250)

    move_wam_from_current_location(experiment_home_point, 2, 250)
    move_wam_from_current_location(experiment_pickup_point, 2, 250)
    close_wam_hand()
    move_wam_from_current_location(experiment_dropoff_point, 2, 250)
    open_wam_hand()
    move_wam_from_current_location(experiment_home_point, 2, 250)
    close_wam_hand_spread()
    move_wam_from_current_location(wam_home, 2, 250)
    '''
