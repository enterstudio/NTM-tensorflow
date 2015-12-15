from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import tensorflow as tf

from layers import *

class NTM(object):
    def __init__(self, config=None):
        self.input_dim = 128
        self.output_dim = 128
        self.mem_size = 128
        self.mem_dim = 20
        self.controller_dim = 100
        self.controller_layer_size = 2
        self.shift_range = 1
        self.write_head_size = 2
        self.read_head_size = 2

        #self.input_dim = config.input_dim or 128
        #self.output_dim = config.output_dim or 128
        #self.mem_size = config.mem_size or 128
        #self.mem_dim = config.mem_dim or 20
        #self.controller_dim = config.controller_dim    or 100
        #self.controller_layer_size = config.controller_layer_size or 1
        #self.shift_range = config.shift_range or 1
        #self.write_head_size = config.write_head_size or 1
        #self.read_heads_size = config.read_heads_size  or 1

        self.depth = 0
        self.cells = {}
        self.master_cell = self.build_cell()
        #self.init_module = self.new_init_module()

        #self:init_grad_inputs()

    # Build a NTM cell which shares weights with "master" cell.
    def build_cell(self):
        input = tf.placeholder(tf.float32, [1, self.input_dim])

        # previous memory state
        M_prev = tf.placeholder(tf.float32, [self.mem_size, self.mem_dim])

        # previous read/write weights
        read_w_prev = tf.placeholder(tf.float32, [self.read_head_size, self.mem_size])
        write_w_prev = tf.placeholder(tf.float32, [self.write_head_size, self.mem_size])

        # previous vector read from memory
        read_prev = tf.placeholder(tf.float32, [1, self.mem_dim])

        # previous LSTM controller output
        output_prev = tf.placeholder(tf.float32, [self.controller_layer_size, self.output_dim])
        hidden_prev = tf.placeholder(tf.float32, [self.controller_layer_size, self.controller_dim])

        # output and hidden states of controller module
        output, hidden = self.build_controller(input, read_prev, output_prev, hidden_prev)

        # last output layer from LSTM controller
        last_output = output if self.controller_layer_size == 1 else output[-1]

        # Build a memory
        M, read_weight, write_weight, read = self.build_memory(M_prev, read_w_prev, write_w_prev, last_output)

    def build_read_head(self, M_prev, read_w_prev, last_output):
        return self.build_head(M_prev, read_w_prev, last_output, True)

    def build_write_head(self, M_prev, write_w_prev, last_output):
        return self.build_head(M_prev, write_w_prev, last_output, False)

    def build_head(self, M_prev, w_prev, last_output, is_read):
        k = tf.tanh(Linear(last_output, self.mem_dim))
        s = tf.nn.softmax(Linear(last_output, 2 * self.shift_range + 1))
        beta  = tf.nn.softplus(Linear(last_output, 1))
        g = tf.sigmoid(Linear(last_output, 1))
        gamma = tf.add(tf.nn.softplus(Linear(last_output, 1)), tf.constant(1))

        # similarity layer
        M_dim_norm = tf.sqrt(tf.reduce_sum(tf.mul(M_prev, M_prev),1))
        k_norm = tf.sqrt(tf.matmul(k,k))
        dot = tf.mul(M_prev, k)
        sim = tf.div(dot, (M_dim_norm * k_norm + 1e-3))

    # build a memory to read & write
    def build_memory(self, M_prev, read_w_prev, write_w_prev, last_output):
        if self.read_head_size == 1:
            write_w, read_w = self.new_read_head(M_prev, read_w_prev, last_output)
        else:
            write_w, read = [], []
            for idx in xrange(self.read_head_size):
                read_w_idx = tf.gather(read_w_prev, idx)
                w, r = self.build_read_head(M_prev, read_w_idx, last_output)
                write_w.append(w)
                read.append(r)

    # Build a LSTM controller
    def build_controller(self, input, read_prev, output_prev, hidden_prev):
        output, hidden = [], []
        for layer_idx in xrange(self.controller_layer_size):
            if self.controller_layer_size == 1:
                o_prev = output_prev
                h_prev = hidden_prev
            else:
                o_prev = tf.reshape(tf.gather(output_prev, layer_idx), [1, -1])
                h_prev = tf.reshape(tf.gather(hidden_prev, layer_idx), [1, -1])

            if layer_idx == 0:
                def new_gate():
                    in_modules = [
                        Linear(input, self.controller_dim),
                        Linear(o_prev, self.controller_dim),
                    ]
                    if self.read_head_size == 1:
                        in_modules.append(
                            Linear(read_prev, self.controller_dim)
                        )
                    else:
                        for read_idx in xrange(self.read_head_size):
                            vec = tf.reshape(tf.gather(read_prev, read_idx), [1, -1])
                            in_modules.append(
                                Linear(vec, self.controller_dim)
                            )
                    return tf.add_n(in_modules)
            else:
                def new_gate():
                    return tf.add_n([
                        Linear(output[layer_idx-1], self.controller_dim),
                        Linear(o_prev, self.controller_dim),
                    ])

            # input, forget, and output gates for LSTM
            i = tf.sigmoid(new_gate())
            f = tf.sigmoid(new_gate())
            o = tf.sigmoid(new_gate())
            update = tf.tanh(new_gate())

            # update the sate of the LSTM cell
            hidden.append(tf.add_n([f * h_prev, i * update]))
            output.append(o * tf.tanh(hidden[layer_idx]))

        return output, hidden
