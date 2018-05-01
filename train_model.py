# Phu, Andrea and Watcher
# 2018 Spring

# Phu, Andrea and Watcher
# 2018 Spring
import torch
import torch.nn as nn
import torch.autograd as autograd
from torch.autograd import Variable
import torch.nn.functional as F
import torch.optim as optim
from torch import FloatTensor, LongTensor
import numpy as np
import pandas as pd
import time
import os
import pickle
import string
import torch.utils.data as data_utils
import psutil
from random import shuffle
from sklearn.utils import shuffle as skshuffle
torch.manual_seed(1)

processed_data_path = '/data/Dropbox/judge_embedding_data_sp18'
all_data_save_path = os.path.join(processed_data_path,"finalized_all_data","all_data_dict.pkl")
all_data_support_save_path = os.path.join(processed_data_path,"finalized_all_data","all_data_dict_support.pkl")
all_data_df_save_path = os.path.join(processed_data_path,"finalized_all_data","all_data_df.h5")
finished_embedding_folder_path = os.path.join(processed_data_path,'finished_judge_embedding')
trained_emb_path = os.path.join(finished_embedding_folder_path,"trained_emb_0.pkl")

def train_val_test_split(data_df,number_judges,train_ratio=0.8,val_ratio=0.1,verbose=0,toshuffle=True):
    starttime= time.time()
    sorted_all_data = data_df.sort_values(by='judge_embed_index')
    train_indexes = []
    val_indexes = []
    test_indexes = []
    currentiloc = 0
    for judge_index in range(number_judges):
        if verbose and judge_index%500 == 0:
            print(judge_index,time.time()-starttime)
        
        cases_of_this_judge = sorted_all_data.loc[sorted_all_data['judge_embed_index'] == judge_index]
        number_cases = cases_of_this_judge.shape[0]
        n_of_train = int(number_cases*train_ratio)
        n_of_val = int(number_cases*val_ratio)
        
        nextiloc = currentiloc+number_cases
        
        indexes = [i for i in range(currentiloc, nextiloc)]
        shuffle(indexes)
        
        train_indexes += indexes[:n_of_train]
        val_indexes += indexes[n_of_train:n_of_train+n_of_val]
        test_indexes += indexes[n_of_train+n_of_val:]
        
        currentiloc = nextiloc
    return skshuffle(data_df.loc[train_indexes]),skshuffle(data_df.loc[val_indexes]),skshuffle(data_df.loc[test_indexes])

def df_to_Tensor(df,topic_glove_emb,verbose=0):
    # use this to convert a dataframe to torch tensor
    feature_dim = 300+300+2
    X = np.zeros((df.shape[0],feature_dim))
    y = np.zeros(df.shape[0])
    
    for i in range(df.shape[0]):
        if verbose and i%10000==0:
            print(i)
        
        data_entry = df.iloc[i]
        
        X[i,:300] = data_entry['opinion_vector']
        topic = data_entry['topic']
        topic = str.lower(str(topic)) 
        
        if topic not in topic_glove_emb: # deal with any unknown topic
            topic = "<UNK>"
            
        X[i,300:600] = topic_glove_emb[topic]
        decision = data_entry['judge_decision']
        X[i,600+decision] = 1 # one hot representation for judge decision
        y[i] = data_entry['judge_embed_index']
        
    return FloatTensor(X),LongTensor(y)

class Judge_emb_model(nn.Module):
    def __init__(self, input_dim, hidden_layer_dim, embedding_dim, num_judges):
        super(Judge_emb_model,self).__init__()
        # input is m x D
        self.linear1 = nn.Linear(input_dim,hidden_layer_dim) # D x H 
        self.dropout1 = nn.Dropout(p=0.5)
        self.linear2 = nn.Linear(hidden_layer_dim,hidden_layer_dim) # H x H
        self.dropout2 = nn.Dropout(p=0.5)
        self.linear3 = nn.Linear(hidden_layer_dim,embedding_dim)
        
        self.judge_embedding = nn.Linear(embedding_dim,num_judges) # H x J
        # the output is m x J
        
        self.init_weights()

    def forward(self, X):
        out = F.relu(self.linear1(X))
        out = self.dropout1(out)
        out = F.relu(self.linear2(out))
        out = self.dropout2(out)
        out = F.relu(self.linear3(out))
        out = self.judge_embedding(out)
        
        # now we have m x J matrix, for m data points, we can do log softmax
        log_prob = F.log_softmax(out,dim=1)
        return log_prob # for each opinion data, this is probability of which judge writes this opinion
    
    def init_weights(self):
        linear_layers = [self.linear1,self.linear2,self.linear3,self.judge_embedding]
        for layer in linear_layers:
            layer.weight.data.normal_(0.0,0.1)


all_data_dict = pickle.load(open(all_data_save_path,"rb"))
topic_glove_emb = all_data_dict['topic_glove_emb'][0]
judgeId2Index = all_data_dict['judge_id_to_index'][0]
judgeIndex2Id = all_data_dict['judge_index_to_id'][0]
all_data_df = all_data_dict['data_df']


data_train, data_val, data_test = train_val_test_split(all_data_df,2099,verbose=0)

X_train, y_train = df_to_Tensor(data_train,topic_glove_emb,1)
X_val, y_val = df_to_Tensor(data_val,topic_glove_emb,1)
X_test, y_test = df_to_Tensor(data_test,topic_glove_emb,1)


BATCH_SIZE = 64
train_dataset = data_utils.TensorDataset(data_tensor=X_train,target_tensor=y_train)
train_loader = data_utils.DataLoader(dataset=train_dataset,batch_size=BATCH_SIZE,shuffle=True)



INPUT_DIM = 602
HIDDEN_DIM = 500
EMBED_DIM = 500
number_judges = 2099
model = Judge_emb_model(input_dim=INPUT_DIM,hidden_layer_dim=HIDDEN_DIM,
                        embedding_dim=EMBED_DIM,num_judges=number_judges)
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters(),lr=0.01)


N_EPOCH = 10
TRAIN_SIZE = train_dataset.data_tensor.shape[0]
print("Training data size",TRAIN_SIZE)
train_losses = []
val_losses = []

X_val_var = Variable(X_val)
y_val_var = Variable(y_val)
model.eval()
y_pred_val = model.forward(X_val_var)
val_loss = criterion(y_pred_val,y_val_var)
print("initial val loss",val_loss.data[0])
startTime = time.time()
model.train()

for i_epoch in range(N_EPOCH):
    epoch_train_loss = 0
    num_batches_per_epoch = int(TRAIN_SIZE/BATCH_SIZE)
    for i_batch,(X_batch, y_batch) in enumerate(train_loader):
        optimizer.zero_grad()
        
        X_var, y_var = Variable(X_batch),Variable(y_batch)
        
        y_pred = model.forward(X_var)
        loss = criterion(y_pred,y_var)
        loss.backward()
        
        optimizer.step()
#         if i_batch % 2000 == 0:
#             print(i_epoch,i_batch,loss.data[0])
        epoch_train_loss += loss.data[0]
        
    # after each epoch
    
    X_val_var = Variable(X_val)
    y_val_var = Variable(y_val)
    model.eval()
    y_pred_val = model.forward(X_val_var)
    val_loss = criterion(y_pred_val,y_val_var)
    ave_train_loss = epoch_train_loss/num_batches_per_epoch
    print("epoch",i_epoch,"ave_train_loss",
          ave_train_loss,"validation loss:",val_loss.data[0],time.time()-startTime)
    val_losses.append(val_loss.data[0])
    train_losses.append(ave_train_loss)
    model.train()
    
trained_emb = model.judge_embedding.weight.data.numpy()    
pickle.dump(trained_emb,open(trained_emb_path,"wb"))
