from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
from six.moves import xrange  
import tensorflow as tf
import utility_function as uf
# import my_seq2seq as mseq
import os
import data_queue
import nt
import time

import con_lstm as clstm

RESTORE = False

FLAGS = tf.app.flags.FLAGS
tf.app.flags.DEFINE_string('num_threads',2,'''the number of threads for enqueue''')
tf.app.flags.DEFINE_string('train_log_dir','auto_logs',
		'''directory wherer to write event logs''')
tf.app.flags.DEFINE_integer('max_training_iter', 100000,
        '''the max number of training iteration''')
tf.app.flags.DEFINE_float('init_learning_rate',0.01,
        '''initial learning rate''')
tf.app.flags.DEFINE_string('model_dir', 'auto_model_logs',
		'''directory where to save the model''')

# INPUT_DIM = 64 * 64
INPUT_H = 64
INPUT_W = 64
INPUT_C = 1
LABEL_C = 1
CELL_C = 32
KSIZE = 5
# LABEL_DIM = INPUT_DIM

CELL_DIM = 1024
CELL_LAYER = 1

BATCH_SIZE = 10
# UNROLLING_NUM = 10
UNROLLING_NUM = 1


def train():
	input_data_queue = data_queue.DATA_QUEUE()
	
	clstm_cell = clstm.con_lstm_cell(10, INPUT_H, INPUT_W, INPUT_C, KSIZE, CELL_C)
	# single_cell = tf.nn.rnn_cell.BasicLSTMCell(CELL_DIM)
	# multi_cell = tf.nn.rnn_cell.MultiRNNCell([single_cell] * CELL_LAYER)

	inputs_ph = list()
	decodes1_ph = list()
	# decodes2_ph = list()
   	for _ in range(UNROLLING_NUM):
		# inputs_ph.append(tf.placeholder(tf.float32,[BATCH_SIZE, INPUT_DIM], name = "input_ph"))
		# decodes1_ph.append(tf.placeholder(tf.float32,[BATCH_SIZE, INPUT_DIM], name = "decodes1_ph"))	
		inputs_ph.append(tf.placeholder(tf.float32,[BATCH_SIZE, INPUT_H, 
						INPUT_W, INPUT_C], name = "input_ph"))
		decodes1_ph.append(tf.placeholder(tf.float32,[BATCH_SIZE, INPUT_H, 
						INPUT_W, INPUT_C], name = "decodes1_ph"))	
		# decodes2_ph.append(tf.placeholder(tf.float32,[BATCH_SIZE, INPUT_DIM], name = "decodes2_ph"))	

	# cell_initial_state = multi_cell.zero_state(BATCH_SIZE, tf.float32)
	cell_initial_state = clstm_cell.get_zero_state(BATCH_SIZE, INPUT_H, INPUT_W, CELL_C, tf.float32)
	# decoder_inputs_dict = dict()
	# decoder_inputs_dict['reconstruction'] = decodes1_ph
	# decoder_inputs_dict['prediction'] = decodes2_ph
	# num_decoder_symbols_dict = dict()
	# num_decoder_symbols_dict["reconstruction"] = 0
	# num_decoder_symbols_dict["prediction"] = 1

	feed_previous_ph = tf.placeholder(tf.bool)
	loss = []
	loop_function = lambda x,y:x	
	with tf.device('/gpu:%d' % 0):
		_, state = clstm.clstm_encode(clstm_cell, inputs_ph, cell_initial_state)
		outputs, state = clstm.clstm_decode(inputs_ph[-1], state, clstm_cell, UNROLLING_NUM)
		# print(outputs)
		con_cat_out = tf.concat(0, outputs)
		# outputs,_ = mseq.no_embedding_one2many_rnn_seq2seq(inputs_ph, decoder_inputs_dict, 
		# 		multi_cell, num_decoder_symbols_dict, feed_previous_ph)
		# 	con_cat_out1 = tf.concat(0, outputs['reconstruction'])
		# 	con_cat_out2 = tf.concat(0, outputs['prediction'])

		infer = nt.inference3(con_cat_out, KSIZE, CELL_C, LABEL_C)
		# con_cat_decodes2 = tf.concat(0, decodes2_ph)
		# infer1 = nt.inference(con_cat_out1, CELL_DIM, LABEL_DIM, scope_name = "pred")	
		# loss1 = nt.loss2(infer1, con_cat_decodes1)
		# infer2 = nt.inference(con_cat_out2, CELL_DIM, LABEL_DIM, scope_name = "recon")	
		# loss2 = nt.loss2(infer2, con_cat_decodes2)
		# loss = loss1 + loss2
		con_cat_decode1 = tf.concat(0, decodes1_ph)
		loss = nt.loss1(infer, con_cat_decode1)

	saver = tf.train.Saver()
	global_step = tf.Variable(0, name = 'global_step', trainable = False)
	train_op = nt.training1(loss, FLAGS.init_learning_rate, global_step = global_step)

	config_proto = uf.define_graph_config(0.2)
	sess = tf.Session(config = config_proto)
	# sess = tf.Session()

	init_op = tf.initialize_all_variables()
	sess.run(init_op)

	if RESTORE:
		ckpt = tf.train.get_checkpoint_state(FLAGS.model_dir)
		print(ckpt.all_model_checkpoint_paths[-1])
		if ckpt and ckpt.all_model_checkpoint_paths[-1]:
			saver.restore(sess, ckpt.all_model_checkpoint_paths[-1])
		else:
			print('no check point')

	coord = tf.train.Coordinator()
	threads = tf.train.start_queue_runners(coord = coord, sess = sess)

	for i in xrange(FLAGS.max_training_iter):
		feed_data = dict()
		for j in xrange(UNROLLING_NUM):
			input_v = input_data_queue.get_next_batch_train(BATCH_SIZE, False, 4)
			# feed_data[inputs_ph[j]] = input_v[j,:,0:INPUT_DIM]
			feed_data[inputs_ph[j]] = input_v[j]
			feed_data[decodes1_ph[j]] = input_v[UNROLLING_NUM - j - 1]
			# feed_data[decodes2_ph[j]] = input_v[10 + j,:,0:INPUT_DIM]
		feed_data[feed_previous_ph] = True
		_, loss_v = sess.run([train_op, loss], feed_dict = feed_data)
		if i % 100 == 0:
			input_v = input_data_queue.get_next_batch_test(BATCH_SIZE, False, 4)
			for j in range(UNROLLING_NUM):
				feed_data[inputs_ph[j]] = input_v[j]
				feed_data[decodes1_ph[j]] = input_v[UNROLLING_NUM - j - 1]
				# feed_data[decodes2_ph[j]] = input_v[10 + j,:,0:INPUT_DIM]
			feed_data[feed_previous_ph] = True
			test_loss_v = sess.run(loss, feed_dict = feed_data)
			disp = "i:%d, train loss:%f, test loss:%f"%(i,loss_v, test_loss_v)
			print(disp)

		if i != 0 and i % 5000 == 0:
			curr_time = time.strftime("%Y%m%d_%H%M")
			model_name = FLAGS.model_dir + '/' + curr_time + '_iter_' + str(i) + '_model.ckpt'
			saver.save(sess,model_name)

def main(argv = None):
    if not os.path.exists(FLAGS.model_dir):
        os.makedirs(FLAGS.model_dir)
    if not os.path.exists(FLAGS.train_log_dir):
        os.makedirs(FLAGS.train_log_dir)
    train()

if __name__ == '__main__':
    tf.app.run()
