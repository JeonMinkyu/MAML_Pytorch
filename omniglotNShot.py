from    omniglot import Omniglot

import torchvision
import torchvision.transforms as transforms
from PIL import Image
import os.path
import numpy as np

class OmniglotNShot():
    def __init__(self, root, batch_size, n_way, k_shot, k_query, img_size):
        self.resize = img_size
        
        if not os.path.isfile(os.path.join(root, 'omni.npy')):
            self.x = Omniglot(root, download=True,
                                transform = transforms.Compose([lambda x: Image.open(x).convert('L'),
                                                            transforms.Resize(self.resize),
                                                            lambda x : np.reshape(x, (self.resize, self.resize, 1)),
                                                            lambda x : x/255.,
                                                            lambda x: np.transpose(x, [2,0,1]),
                                                            ]))
            
            temp = dict() #{label : img1, img2, ..., 20 imgs in total, 1623 label}
            # len(self.x) # 32460 = 20 * 1623
            for (img, label) in self.x:
                if label in temp:
                    # img :[1,28,28]
                    temp[label].append(img)
                else:
                    temp[label] = [img]
                    
            self.x = []
            for label, imgs in temp.items():
                self.x.append(np.array(imgs))
                
            self.x = np.array(self.x) # [[20 imgs], ... , 1623 classes in total]

            temp = [] # Free memory
            np.save(os.path.join(root, 'omni.npy'), self.x)
        
        else:
            self.x = np.load(os.path.join(root, 'omni.npy'))
        
        # x : [1623, 20, 1, 28, 28]
        np.random.shuffle(self.x) # shuffle on the first dim = 1623 cls
        self.x_train, self.x_test = self.x[:1200], self.x[1200:]
        
        # normalization
        self.x_train = (self.x_train - np.mean(self.x_train)) / np.std(self.x_train)
        self.x_test = (self.x_test - np.mean(self.x_test)) / np.std(self.x_test)
        
        self.batch_size = batch_size
        self.n_class = self.x.shape[0] # 1623
        self.n_way = n_way
        self.k_shot = k_shot
        self.k_query = k_query
        
        self.indexes = {"train": 0, "test": 0}
        self.datasets = {"train": self.x_train, "test": self.x_test}
        
        self.datasets_cache = {"train": self.load_data_cache(self.datasets["train"]),
                               "test": self.load_data_cache(self.datasets["test"])}
        # len(self.datasets_cache['train'])) : 50
        # self.datasets_cache['train'][0][0] : [32,5,1,28,28]
        # self.datasets_cache['train'][0][1] : [32,5]
    def load_data_cache(self, data_pack):
        """
        Collects several batches data for N-shot learning
        N shot Learning을 한 data batches
        data_pack : [class_num, 20, 1, 28, 28] #class_num : train일 때 1200, test는 423
        return : A list [support_set_x, support_set_y, target_x, target_y] ready to be fed to our networks
        """
        
        dataset_size = self.k_shot * self.n_way
        query_size = self.k_query * self.n_way
        data_cache = []

        for sample in range(100): # num of eisodes

            support_x = np.zeros((self.batch_size, dataset_size, 1, self.resize, self.resize)) # [32, 5, 28, 28, 1]
            support_y = np.zeros((self.batch_size, dataset_size), dtype=np.int)
            query_x = np.zeros((self.batch_size, query_size, 1, self.resize, self.resize)) # [32, 5, 28, 28, 1]
            query_y = np.zeros((self.batch_size, query_size), dtype=np.int)

            for i in range(self.batch_size):
                shuffle_idx = np.arange(self.n_way) # [0,1,2,3,4]
                np.random.shuffle(shuffle_idx) # [2,4,1,0,3]
                shuffle_idx_test = np.arange(self.n_way) # [0,1,2,3,4]
                np.random.shuffle(shuffle_idx_test) # [2,0,1,4,3]

                selected_cls = np.random.choice(data_pack.shape[0], self.n_way, replace=False)
                for j, cur_class in enumerate(selected_cls):
                    # cur_class : count the case in meta_test
                    selected_imgs = np.random.choice(data_pack.shape[1], self.k_shot+self.k_query, replace=False) # # Select k_shot + k_query in 20

                    # Divide support and query set in meta-train dataset
                    # support_set for meta training
                    for offset, img in enumerate(selected_imgs[:self.k_shot]):
                        # i :batch_idx, cur_class : class in n_way
                        support_x[i, shuffle_idx[j]*self.k_shot+offset, ...] = data_pack[cur_class][img]
                        support_y[i, shuffle_idx[j]*self.k_shot+offset] = j

                    # query_set for meta testing
                    for offset, img in enumerate(selected_imgs[self.k_shot:]):
                        query_x[i, shuffle_idx_test[j]*self.k_query+offset, ...] = data_pack[cur_class][img]
                        query_y[i, shuffle_idx_test[j]*self.k_query+offset] = j

            data_cache.append([support_x, support_y, query_x, query_y])
        return data_cache

    def get_batch(self, mode):
        # mode : train / test
        # Gets next batch from the dataset with name.

        if self.indexes[mode] >= len(self.datasets_cache[mode]):
            self.indexes[mode] = 0
            self.datasets_cache[mode] = self.load_data_cache(self.datasets[mode])

        # len(self.datasets_cache['train'])) : 100
        next_batch = self.datasets_cache[mode][self.indexes[mode]]
        self.indexes[mode] += 1 

        return next_batch