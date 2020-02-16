#!/usr/bin/env python

'''
Based on: 
https://github.com/vmayoral/basic_reinforcement_learning
https://gist.github.com/wingedsheep/4199594b02138dd427c22a540d6d6b8d
https://github.com/goelshivam1210/human_robot_interaction/blob/master/gym-gazebo/examples/scripts_turtlebot/smarthome_turtlebot_lidar_camera_dqn.py

#modified by: Abhijay
#email: abhijay@pdx.edu

# Changes: Added attention layer
'''
import gym
import gym_gazebo
import time
from distutils.dir_util import copy_tree
import os
import json
import random
import numpy as np
from keras.models import Sequential, load_model
from keras import initializers
from keras import regularizers
from keras.models import Model
from keras.layers import Input, Dense, multiply,LeakyReLU
import memory

class DeepQ:
	"""
	DQN abstraction.

	As a quick reminder:
		traditional Q-learning:
			Q(s, a) += alpha * (reward(s,a) + gamma * max(Q(s') - Q(s,a))
		DQN:
			target = reward(s,a) + gamma * max(Q(s')

	"""
	def __init__(self, inputs, outputs, memorySize, discountFactor, learningRate, learnStart):
		"""
		Parameters:
			- inputs: input size
			- outputs: output size
			- memorySize: size of the memory that will store each state
			- discountFactor: the discount factor (gamma)
			- learningRate: learning rate
			- learnStart: steps to happen before for learning. Set to 128
		"""
		self.input_size = inputs
		self.output_size = outputs
		self.memory = memory.Memory(memorySize)
		self.discountFactor = discountFactor
		self.learnStart = learnStart
		self.learningRate = learningRate

	def initNetworks(self, hiddenLayers):
		model = self.createModel(self.input_size, self.output_size, hiddenLayers, "relu", self.learningRate)
		self.model = model

		targetModel = self.createModel(self.input_size, self.output_size, hiddenLayers, "relu", self.learningRate)
		self.targetModel = targetModel

	def createRegularizedModel(self, inputs, outputs, hiddenLayers, activationType, learningRate):
		bias = True
		dropout = 0
		regularizationFactor = 0.01
		model = Sequential()
		if len(hiddenLayers) == 0: 
			model.add(Dense(self.output_size, input_shape=(self.input_size,), init='lecun_uniform', bias=bias))
			model.add(Activation("linear"))
		else :
			if regularizationFactor > 0:
				model.add(Dense(hiddenLayers[0], input_shape=(self.input_size,), init='lecun_uniform', W_regularizer=l2(regularizationFactor),  bias=bias))
			else:
				model.add(Dense(hiddenLayers[0], input_shape=(self.input_size,), init='lecun_uniform', bias=bias))

			if (activationType == "LeakyReLU") :
				model.add(LeakyReLU(alpha=0.01))
			else :
				model.add(Activation(activationType))
			
			for index in range(1, len(hiddenLayers)):
				layerSize = hiddenLayers[index]
				if regularizationFactor > 0:
					model.add(Dense(layerSize, init='lecun_uniform', W_regularizer=l2(regularizationFactor), bias=bias))
				else:
					model.add(Dense(layerSize, init='lecun_uniform', bias=bias))
				if (activationType == "LeakyReLU") :
					model.add(LeakyReLU(alpha=0.01))
				else :
					model.add(Activation(activationType))
				if dropout > 0:
					model.add(Dropout(dropout))
			model.add(Dense(self.output_size, init='lecun_uniform', bias=bias))
			model.add(Activation("linear"))
		optimizer = optimizers.RMSprop(lr=learningRate, rho=0.9, epsilon=1e-06)
		model.compile(loss="mse", optimizer=optimizer)
		model.summary()
		return model

	def createModel(self, inputs, outputs, hiddenLayers, activationType, learningRate):
		model = Sequential()
		if len(hiddenLayers) == 0: 
			model.add(Dense(self.output_size, input_shape=(self.input_size,), init='lecun_uniform'))
			model.add(Activation("linear"))
		# this seems to be the attention part 
		else :
			input_dims = self.input_size
			inputs = Input(shape=(input_dims,))

			AttentionFlag = True # Set False for experiment without Attention
			if AttentionFlag:
				attention_probs = Dense(input_dims, activation='sigmoid', kernel_initializer=initializers.glorot_uniform(seed=None), bias_initializer='zeros', name='attention_probs')(inputs)
				attention_mul = multiply([inputs, attention_probs], name='attention_mul')
			else:
				x = Dense(hiddenLayers[0], kernel_initializer=initializers.glorot_uniform(seed=None), name='dense_1')(inputs)

			if AttentionFlag:
				x = Dense(hiddenLayers[0], kernel_initializer=initializers.glorot_uniform(seed=None), name='dense_1')(attention_mul)

			lr = LeakyReLU(alpha=0.01, name='lr_1')(x)

			for index in range(1, len(hiddenLayers)):
				layerSize = hiddenLayers[index]
				x = Dense(hiddenLayers[0], kernel_initializer=initializers.glorot_uniform(seed=None), name='dense_'+str(index+1))(lr)
				lr = LeakyReLU(alpha=0.01, name='lr_'+str(index+1))(x)

			output = Dense(self.output_size, kernel_initializer=initializers.glorot_uniform(seed=None), activation='linear', name='dense_out')(lr)
			model = Model(input=[inputs], output=output)
			model.compile(optimizer='adam',
						  loss='mse',)
						  # metrics=['accuracy'])
			model.summary()
			return model

	def printNetwork(self):
		i = 0
		for layer in self.model.layers:
			weights = layer.get_weights()
			print "layer ",i,": ",weights
			i += 1


	def backupNetwork(self, model, backup):
		weightMatrix = []
		for layer in model.layers:
			weights = layer.get_weights()
			weightMatrix.append(weights)
		i = 0
		for layer in backup.layers:
			weights = weightMatrix[i]
			layer.set_weights(weights)
			i += 1

	def updateTargetNetwork(self):
		self.backupNetwork(self.model, self.targetModel)

	# predict Q values for all the actions
	def getQValues(self, state):
		predicted = self.model.predict(state.reshape(1,len(state)))
		#print (np.shape(predicted))
		return predicted[0]

	def getTargetQValues(self, state):
		#predicted = self.targetModel.predict(state.reshape(1,len(state)))
		predicted = self.targetModel.predict(state.reshape(1,len(state)))

		return predicted[0]

	def getMaxQ(self, qValues):
		return np.max(qValues)

	def getMaxIndex(self, qValues):
		return np.argmax(qValues)

	# calculate the target function
	def calculateTarget(self, qValuesNewState, reward, isFinal):
		"""
		target = reward(s,a) + gamma * max(Q(s')
		"""
		if isFinal:
			return reward
		else : 
			return reward + self.discountFactor * self.getMaxQ(qValuesNewState)

	# select the action with the highest Q value
	def selectAction(self, qValues, explorationRate):
		rand = random.random()
		if rand < explorationRate :
			action = np.random.randint(0, self.output_size)
		else :
			action = self.getMaxIndex(qValues)
		return action

	def selectActionByProbability(self, qValues, bias):
		qValueSum = 0
		shiftBy = 0
		for value in qValues:
			if value + shiftBy < 0:
				shiftBy = - (value + shiftBy)
		shiftBy += 1e-06

		for value in qValues:
			qValueSum += (value + shiftBy) ** bias

		probabilitySum = 0
		qValueProbabilities = []
		for value in qValues:
			probability = ((value + shiftBy) ** bias) / float(qValueSum)
			qValueProbabilities.append(probability + probabilitySum)
			probabilitySum += probability
		qValueProbabilities[len(qValueProbabilities) - 1] = 1

		rand = random.random()
		i = 0
		for value in qValueProbabilities:
			if (rand <= value):
				return i
			i += 1

	def addMemory(self, state, action, reward, newState, isFinal):
		self.memory.addMemory(state, action, reward, newState, isFinal)

	def learnOnLastState(self):
		if self.memory.getCurrentSize() >= 1:
			return self.memory.getMemory(self.memory.getCurrentSize() - 1)

	def learnOnMiniBatch(self, miniBatchSize, useTargetNetwork=True):
		# Do not learn until we've got self.learnStart samples        
		if self.memory.getCurrentSize() > self.learnStart:
			# learn in batches of 128
			miniBatch = self.memory.getMiniBatch(miniBatchSize)
			X_batch = np.empty((0,self.input_size), dtype = np.float64)
			Y_batch = np.empty((0,self.output_size), dtype = np.float64)
			for sample in miniBatch:
				isFinal = sample['isFinal']
				state = sample['state']
				action = sample['action']
				reward = sample['reward']
				newState = sample['newState']

				qValues = self.getQValues(state)
				if useTargetNetwork:
					qValuesNewState = self.getTargetQValues(newState)
				else :
					qValuesNewState = self.getQValues(newState)
				targetValue = self.calculateTarget(qValuesNewState, reward, isFinal)

				X_batch = np.append(X_batch, np.array([state.copy()]), axis=0)
				Y_sample = qValues.copy()
				Y_sample[action] = targetValue
				Y_batch = np.append(Y_batch, np.array([Y_sample]), axis=0)
				if isFinal:
					X_batch = np.append(X_batch, np.array([newState.copy()]), axis=0)
					Y_batch = np.append(Y_batch, np.array([[reward]*self.output_size]), axis=0)
			self.model.fit(X_batch, Y_batch, batch_size = len(miniBatch), nb_epoch=1, verbose = 0)

	def saveModel(self, path):
		self.model.save(path)

	def loadWeights(self, path):
		self.model.set_weights(load_model(path).get_weights())

def detect_monitor_files(training_dir):
	return [os.path.join(training_dir, f) for f in os.listdir(training_dir) if f.startswith('openaigym')]

def clear_monitor_files(training_dir):
	files = detect_monitor_files(training_dir)
	if len(files) == 0:
		return
	for file in files:
		print file
		os.unlink(file)

if __name__ == '__main__':

	#REMEMBER!: turtlebot_nn_setup.bash must be executed.
	#env = gym.make('GazeboCircuit2TurtlebotLidarNn-v0')
	#env = gym.make('GazeboHumanSmartHomeTurtlebotLidarCameraNn-v0')
	env = gym.make('GazeboHumanSmartHomeTurtlebotLidarCameraNn-v0')
	outdir = 'models/gazebo_gym_experiments/'
	#print("Action Space: ", env.action_space)

	continue_execution = False
	#fill this if continue_execution=True
	#continue_execution = True

	#weights_path = '/tmp/turtle_c2_dqn_ep200.h5' 
	#monitor_path = '/tmp/turtle_c2_dqn_ep200'
	#params_json  = '/tmp/turtle_c2_dqn_ep200.json'

	if not continue_execution:
		#Each time we take a sample and update our weights it is called a mini-batch. 
		#Each time we run through the entire dataset, it's called an epoch.
		#PARAMETER LIST
		epochs = 10000
		steps = 10000
		updateTargetNetwork = 10000
		explorationRate = 1
		minibatch_size = 64
		learnStart = 64
		learningRate = 0.00025
		discountFactor = 0.99
		memorySize = 1000000
		network_inputs = 118
		#network_inputs = 100
		#network_inputs = 20
		network_outputs = 4
		network_layers = [300,300]
		current_epoch = 0

		deepQ = DeepQ(network_inputs, network_outputs, memorySize, discountFactor, learningRate, learnStart)
		deepQ.initNetworks(network_layers)
		env.monitor.start(outdir, force=True, seed=None)
		#print (current_epoch)
	else:
		#Load weights, monitor info and parameter info.
		#ADD TRY CATCH fro this else
		with open(params_json) as outfile:
			d = json.load(outfile)
			epochs = d.get('epochs')
			steps = d.get('steps')
			updateTargetNetwork = d.get('updateTargetNetwork')
			explorationRate = d.get('explorationRate')
			minibatch_size = d.get('minibatch_size')
			learnStart = d.get('learnStart')
			learningRate = d.get('learningRate')
			discountFactor = d.get('discountFactor')
			memorySize = d.get('memorySize')
			network_inputs = d.get('network_inputs')
			network_outputs = d.get('network_outputs')
			network_layers = d.get('network_structure')
			current_epoch = d.get('current_epoch')

		deepQ = DeepQ(network_inputs, network_outputs, memorySize, discountFactor, learningRate, learnStart)
		deepQ.initNetworks(network_layers)
		deepQ.loadWeights(weights_path)

		clear_monitor_files(outdir)
		copy_tree(monitor_path,outdir)
		env.monitor.start(outdir, resume=True, seed=None)

	last100Scores = [0] * 100
	last100ScoresIndex = 0
	last100Filled = False
	stepCounter = 0
	highest_reward = 0
	highest_reward_col = 0
	start_time = time.time()
	#print (start_time)
	#print ("--------------------------")
	#print (env)
	#print ("--------------------------")

	#start iterating from 'current epoch'.

	for epoch in xrange(current_epoch+1, epochs+1, 1):
		# at this step we might want to send the information to the env about the episode number
		# to adjust the reward function accordingly
		observation = env.reset()
		env.update_episode_number(epoch)
		#print (observation)
		cumulated_reward = 0.
		cumulated_reward_collision = 0.
		# number of timesteps
		for t in xrange(steps):
			# env.render()
			qValues = deepQ.getQValues(observation)

			action = deepQ.selectAction(qValues, explorationRate)
			#print ("ACTION===>>> {}".format(action))
			newObservation, reward, done, info = env.step(action)
			#print ("Information received from the environment {}".format(info[0]))
			#print "R: {}  ".format(reward) 
			#print "Observation: {}".format(newObservation)
			
			cumulated_reward_collision += info[0]
			if highest_reward_col < cumulated_reward_collision:
				highest_reward_col = cumulated_reward_collision

			cumulated_reward += reward
			if highest_reward < cumulated_reward:
				highest_reward = cumulated_reward

			deepQ.addMemory(observation, action, reward, newObservation, done)

			if stepCounter >= learnStart:
				if stepCounter <= updateTargetNetwork:
					deepQ.learnOnMiniBatch(minibatch_size, False)
				else :
					deepQ.learnOnMiniBatch(minibatch_size, True)

			observation = newObservation

			if (t >= 1000):
				print ("reached the end! :D")
				done = True

			env.monitor.flush(force=True)
			if done:
				if epoch==1:
					deepQ.saveModel('/usr/local/gym/gym-gazebo/examples/scripts_turtlebot/models/turtle_c2_dqn_ep'+str(epoch)+'.h5')
				last100Scores[last100ScoresIndex] = t
				last100ScoresIndex += 1
				if last100ScoresIndex >= 100:
					last100Filled = True
					last100ScoresIndex = 0
					print ("EP "+str(epoch)+" - {} timesteps".format(t+1)+" -Cumulated R: "+str(reward)+" -Collision R: "+str(cumulated_reward_collision)+" Exploration="+str(round(explorationRate, 2)))
				else :
					m, s = divmod(int(time.time() - start_time), 60)
					h, m = divmod(m, 60)
					print ("EP "+str(epoch)+" - {} timesteps".format(t+1)+" - last100 Steps : "+str((sum(last100Scores)/len(last100Scores)))+" - Cumulated R: "+str(cumulated_reward)+" -Collision R: "+str(cumulated_reward_collision)+"  Eps="+str(round(explorationRate, 2))+"     Time: %d:%02d:%02d" % (h, m, s))
					if (epoch)%100==0:
						#save model weights and monitoring data every 100 epochs. 
						deepQ.saveModel('/usr/local/gym/gym-gazebo/examples/scripts_turtlebot/models/turtle_c2_dqn_withAtt_ep'+str(epoch)+'.h5')
						env.monitor.flush()
						copy_tree(outdir,'/usr/local/gym/gym-gazebo/examples/scripts_turtlebot/models/turtle_c2_dqn_withAtt_ep'+str(epoch))
						#save simulation parameters.
						parameter_keys = ['epochs','steps','updateTargetNetwork','explorationRate','minibatch_size','learnStart','learningRate','discountFactor','memorySize','network_inputs','network_outputs','network_structure','current_epoch']
						parameter_values = [epochs, steps, updateTargetNetwork, explorationRate, minibatch_size, learnStart, learningRate, discountFactor, memorySize, network_inputs, network_outputs, network_layers, epoch]
						parameter_dictionary = dict(zip(parameter_keys, parameter_values))
						with open('models/turtle_c2_dqn_withAtt_ep'+str(epoch)+'.json', 'w') as outfile:
							json.dump(parameter_dictionary, outfile)
				break

			stepCounter += 1
			if stepCounter % updateTargetNetwork == 0:
				deepQ.updateTargetNetwork()
				print ("updating target network")

		explorationRate *= 0.995 #epsilon decay
		# explorationRate -= (2.0/epochs)
		explorationRate = max (0.05, explorationRate)

	env.monitor.close()
	env.close()
