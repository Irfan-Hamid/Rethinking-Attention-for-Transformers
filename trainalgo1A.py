from model2 import build_transformer
from datasetA import BilingualDataset, causal_mask
from config import get_config, get_weights_file_path, latest_weights_file_path
from datasetA import causal_mask_with_future

import torchtext.datasets as datasets
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader, random_split
from torch.optim.lr_scheduler import LambdaLR

import nltk
import matplotlib.pyplot as plt
from nltk.translate.bleu_score import corpus_bleu
from nltk.translate.nist_score import corpus_nist
from torchmetrics import BLEUScore
# from nltk.translate.meteor_score import meteor_score
from nltk.translate.bleu_score import SmoothingFunction
import jiwer
import jiwer
from torchmetrics.functional import char_error_rate, word_error_rate

from torchmetrics.text import BLEUScore

import torch
import numpy as np
import random


import warnings
from tqdm import tqdm
import os
from pathlib import Path

# Huggingface datasets and tokenizers
from datasets import load_dataset
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.trainers import WordLevelTrainer
from tokenizers.pre_tokenizers import Whitespace


import torchmetrics
from torch.utils.tensorboard import SummaryWriter

from nltk.translate.bleu_score import corpus_bleu
from nltk.translate.bleu_score import SmoothingFunction

import nltk

from nltk.tokenize import word_tokenize
from nltk.translate.bleu_score import corpus_bleu
from nltk.translate.bleu_score import corpus_bleu
from nltk.translate.meteor_score import meteor_score


import math
import numpy as np
import sacrebleu
import collections
import nltk

from collections import Counter
from nltk.util import ngrams


def set_seed(seed_value):
    """Set seed for reproducibility."""
    random.seed(seed_value)
    np.random.seed(seed_value)
    torch.manual_seed(seed_value)
    torch.cuda.manual_seed_all(seed_value) 
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

seed_value = 3
set_seed(seed_value)

nltk.download('punkt')
nltk.download('wordnet')
nltk.download('wordnet_ic')

def greedy_decode(model, source, source_mask, tokenizer_src, tokenizer_tgt, max_len, device):
    sos_idx = tokenizer_tgt.token_to_id('[SOS]')
    eos_idx = tokenizer_tgt.token_to_id('[EOS]')

    # Precompute the encoder output and reuse it for every step
    encoder_output = model.encode(source, source_mask)
    # Initialize the decoder input with the sos token
    decoder_input = torch.full((1, 1), fill_value=sos_idx, dtype=torch.long, device=device)
    while True:
        if decoder_input.size(1) >= max_len:
            break

        # Build mask for target
        decoder_mask = causal_mask(decoder_input.size(1)).to(device)

        # Calculate output
        out = model.decode(encoder_output, source_mask, decoder_input, decoder_mask)

        # Get next token
        prob = model.project(out[:, -1])
        _, next_word = torch.max(prob, dim=1)
        next_word = next_word.item()

        # Append next token to decoder input
        decoder_input = torch.cat([decoder_input, torch.tensor([[next_word]], device=device)], dim=1)

        if next_word == eos_idx:
            break

    return decoder_input.squeeze(0)

def run_validation(model, validation_ds, tokenizer_src, tokenizer_tgt, max_len, device, print_msg, global_step, writer):
    model.eval()

    source_texts = []
    expected = []
    predicted = []

    try:
        # get the console window width
        with os.popen('stty size', 'r') as console:
            _, console_width = console.read().split()
            console_width = int(console_width)
    except:
        # If we can't get the console width, 80 as default
        console_width = 80

    with torch.no_grad():
        for batch in validation_ds:
            encoder_input = batch["encoder_input"].to(device) # (b, seq_len)
            encoder_mask = batch["encoder_mask"].to(device) # (b, 1, 1, seq_len)

            # check that the batch size is 1
            assert encoder_input.size(
                0) == 1, "Batch"

            model_out = greedy_decode(model, encoder_input, encoder_mask, tokenizer_src, tokenizer_tgt, max_len, device)

        
            source_text = batch["src_text"][0]
            target_text = batch["tgt_text"][0]
            model_out_text = tokenizer_tgt.decode(model_out.detach().cpu().numpy())

            source_texts.append(source_text)
            expected.append(target_text)
            predicted.append(model_out_text)

    expected_for_bleu = [[exp] for exp in expected]

    bleu = sacrebleu.corpus_bleu(predicted, expected_for_bleu)
    print(f"BLEU score: {bleu.score:.2f}")
        
def greedy_decode_whole(model_causal_mask, model_causal_mask_with_future, source, source_mask, tokenizer_tgt, max_len, device):
    sos_idx = tokenizer_tgt.token_to_id('[SOS]')
    eos_idx = tokenizer_tgt.token_to_id('[EOS]')

    decoder_input = torch.empty(1, 1).fill_(sos_idx).type_as(source).to(device)

    
    encoder_output = model_causal_mask.encode(source, source_mask)

    while decoder_input.size(1) < max_len:
       
        decoder_mask = causal_mask(decoder_input.size(1)).type_as(source_mask).to(device)
        out = model_causal_mask.decode(encoder_output, source_mask, decoder_input, decoder_mask)
        prob = model_causal_mask.project(out[:, -1])
        _, next_word = torch.max(prob, dim=1)

        
        decoder_input = torch.cat([decoder_input, torch.empty(1, 1).type_as(source).fill_(next_word.item()).to(device)], dim=1)

        if next_word.item() == eos_idx:
            decoder_input = torch.cat([decoder_input, next_word.unsqueeze(0)], dim=1)
            break

        
        if decoder_input.size(1) > 4:  
            
            refinement_segment = decoder_input
            refinement_mask = causal_mask_with_future(refinement_segment.size(1)).type_as(source_mask).to(device)
            refinement_out = model_causal_mask_with_future.decode(encoder_output, source_mask, refinement_segment, refinement_mask)
            refinement_prob = model_causal_mask_with_future.project(refinement_out[:, -3])  
            _, refined_word = torch.max(refinement_prob, dim=1)

           
            decoder_input[:, -2] = refined_word

    return decoder_input.squeeze(0)
        
def validate_train_model_whole(model_causal_mask, model_causal_mask_with_future, validation_ds, tokenizer_src, tokenizer_tgt, max_len, device, print_msg, global_step, writer):
    model_causal_mask.eval()
    model_causal_mask_with_future.eval()

    source_texts = []
    expected = []
    predicted_whole = []

    try:
        with os.popen('stty size', 'r') as console:
            _, console_width = console.read().split()
            console_width = int(console_width)
    except:
        console_width = 80

    with torch.no_grad():
        for batch in validation_ds:
            
            encoder_input = batch["encoder_input"].to(device)
            encoder_mask = batch["encoder_mask"].to(device)
            assert encoder_input.size(0) == 1, "Batch"

            model_out_whole = greedy_decode_whole(model_causal_mask, model_causal_mask_with_future, encoder_input, encoder_mask, tokenizer_tgt, max_len, device)

            source_text = batch["src_text"][0]
            target_text = batch["tgt_text"][0]
            model_out_whole_text = tokenizer_tgt.decode(model_out_whole.detach().cpu().numpy())

            source_texts.append(source_text)
            expected.append(target_text)
            predicted_whole.append(model_out_whole_text)
        
    expected_for_bleu = [[exp] for exp in expected]

    bleu = sacrebleu.corpus_bleu(predicted_whole, expected_for_bleu)
    print(f"BLEU score: {bleu.score:.2f}")

def get_all_sentences(ds, lang):
    for item in ds:
        yield item['translation'][lang]

def get_or_build_tokenizer(config, ds, lang):
    tokenizer_path = Path(config['tokenizer_file'].format(lang))
    if not Path.exists(tokenizer_path):
        tokenizer = Tokenizer(WordLevel(unk_token="[UNK]"))
        tokenizer.pre_tokenizer = Whitespace()
        trainer = WordLevelTrainer(special_tokens=["[UNK]", "[PAD]", "[SOS]", "[EOS]"], min_frequency=2)
        tokenizer.train_from_iterator(get_all_sentences(ds, lang), trainer=trainer)
        tokenizer.save(str(tokenizer_path))
    else:
        tokenizer = Tokenizer.from_file(str(tokenizer_path))
    return tokenizer

def get_ds(config):
    ds_raw = load_dataset(f"{config['datasource']}", f"{config['lang_src']}-{config['lang_tgt']}", split='train')

    tokenizer_src = get_or_build_tokenizer(config, ds_raw, config['lang_src'])
    tokenizer_tgt = get_or_build_tokenizer(config, ds_raw, config['lang_tgt'])

    # Keep 90% for training, 10% for validation
    train_ds_size = int(0.9 * len(ds_raw))
    val_ds_size = len(ds_raw) - train_ds_size
    train_ds_raw, val_ds_raw = random_split(ds_raw, [train_ds_size, val_ds_size])

    train_ds = BilingualDataset(train_ds_raw, tokenizer_src, tokenizer_tgt, config['lang_src'], config['lang_tgt'], config['seq_len'])
    val_ds = BilingualDataset(val_ds_raw, tokenizer_src, tokenizer_tgt, config['lang_src'], config['lang_tgt'], config['seq_len'])

    max_len_src = 0
    max_len_tgt = 0

    for item in ds_raw:
        src_ids = tokenizer_src.encode(item['translation'][config['lang_src']]).ids
        tgt_ids = tokenizer_tgt.encode(item['translation'][config['lang_tgt']]).ids
        max_len_src = max(max_len_src, len(src_ids))
        max_len_tgt = max(max_len_tgt, len(tgt_ids))

    print(f'Max length of source sentence: {max_len_src}')
    print(f'Max length of target sentence: {max_len_tgt}')
    

    train_dataloader = DataLoader(train_ds, batch_size=config['batch_size'], shuffle=True)
    val_dataloader = DataLoader(val_ds, batch_size=1, shuffle=True)

    return train_dataloader, val_dataloader, tokenizer_src, tokenizer_tgt

def get_model(config, vocab_src_len, vocab_tgt_len):
    model = build_transformer(vocab_src_len, vocab_tgt_len, config["seq_len"], config['seq_len'], d_model=config['d_model'])
    return model

def train_model_causal_mask(config,current_epoch, model, device, num_epochs):
    config['experiment_name'] = "runs/tmodel_causal_mask"  
    # Define the device
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("Using device:", device)
    if (device == 'cuda'):
        print(f"Device name: {torch.cuda.get_device_name(torch.cuda.current_device())}")
        print(f"Device memory: {torch.cuda.get_device_properties(torch.cuda.current_device()).total_memory / 1024 ** 3} GB")
    elif (device == 'mps'):
        print(f"Device name: <mps>")
    else:
        print("NOTE: If you have a GPU, consider using it for training.")
    device = torch.device(device)

    # Make sure the weights folder exists
    Path(config['model_folder']).mkdir(parents=True, exist_ok=True)

    train_dataloader, val_dataloader, tokenizer_src, tokenizer_tgt = get_ds(config)

    if model is None:
        model = get_model(config, tokenizer_src.get_vocab_size(), tokenizer_tgt.get_vocab_size()).to(device)
    
    # Tensorboard
    writer = SummaryWriter(config['experiment_name'])

    optimizer = torch.optim.Adam(model.parameters(), lr=config['lr'], eps=1e-9)

    initial_epoch = 0
    global_step = 0
    preload = config['preload']
    model_filename = latest_weights_file_path(config) if preload == 'latest' else get_weights_file_path(config, preload) if preload else None
    if model_filename:
        print(f'Preloading model {model_filename}')
        state = torch.load(model_filename)
        model.load_state_dict(state['model_state_dict'])
        initial_epoch = state['epoch'] + 1
        optimizer.load_state_dict(state['optimizer_state_dict'])
        global_step = state['global_step']
    else:
        print('No model to preload, starting from scratch')

    loss_fn = nn.CrossEntropyLoss(ignore_index=tokenizer_src.token_to_id('[PAD]'), label_smoothing=0.1).to(device)

    total_loss = 0  # Initialize total loss accumulator
    num_batches = 0  # Initialize batch counter

    epoch = current_epoch
    torch.cuda.empty_cache()
    model.train()

    print(f"Epoch {epoch}: Training with causal mask")

    batch_iterator = tqdm(train_dataloader, desc=f"Epoch {epoch:02d} - Training with causal mask")
    for batch in batch_iterator:

        encoder_input = batch['encoder_input'].to(device) # (b, seq_len)
        decoder_input = batch['decoder_input'].to(device) # (B, seq_len)
        encoder_mask = batch['encoder_mask'].to(device) # (B, 1, 1, seq_len)
        decoder_mask = batch['decoder_mask'].to(device) # (B, 1, seq_len, seq_len)

        # Run the tensors through the encoder, decoder and the projection layer
        encoder_output = model.encode(encoder_input, encoder_mask) # (B, seq_len, d_model)
        decoder_output = model.decode(encoder_output, encoder_mask, decoder_input, decoder_mask) # (B, seq_len, d_model)
        proj_output = model.project(decoder_output) # (B, seq_len, vocab_size)

        label = batch['label'].to(device) # (B, seq_len)

        loss = loss_fn(proj_output.view(-1, tokenizer_tgt.get_vocab_size()), label.view(-1))
        batch_iterator.set_postfix({"loss": f"{loss.item():6.3f}"})

        writer.add_scalar('train loss/causal_mask', loss.item(), global_step)
        writer.flush()

        
        loss.backward()

        optimizer.step()
        optimizer.zero_grad(set_to_none=True)

        total_loss += loss.item()  # Accumulate loss
        num_batches += 1  # Increment batch counter

        global_step += 1

    average_loss = total_loss / num_batches  # Compute average loss    

    model_filename = get_weights_file_path(config, f"causal_mask_epoch_{epoch:02d}")
    torch.save({
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'global_step': global_step
        }, model_filename)

    return model, average_loss 

def train_model_causal_mask_with_future(config, current_epoch, model_causal_mask, model_causal_mask_with_future, device, num_epochs):
    config['experiment_name'] = "runs/tmodel_causal_mask_with_future"  
    # Define the device
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("Using device:", device)
    device = torch.device(device)

    # Make sure the weights folder exists
    Path(config['model_folder']).mkdir(parents=True, exist_ok=True)

    train_dataloader, val_dataloader, tokenizer_src, tokenizer_tgt = get_ds(config)

    # Only initialize a new model if one isn't provided
    if model_causal_mask_with_future is None:
        model_causal_mask_with_future = get_model(config, tokenizer_src.get_vocab_size(), tokenizer_tgt.get_vocab_size()).to(device)

    writer = SummaryWriter(config['experiment_name'])  # Modify experiment name

    optimizer = torch.optim.Adam(model_causal_mask_with_future.parameters(), lr=config['lr'], eps=1e-9)

    initial_epoch = 0
    global_step = 0
    preload = config['preload']
    model_filename = latest_weights_file_path(config) if preload == 'latest' else get_weights_file_path(config, preload) if preload else None
    if model_filename:
        print(f'Preloading model {model_filename}')
        state = torch.load(model_filename)
        model_causal_mask_with_future.load_state_dict(state['model_state_dict'])
        initial_epoch = state['epoch'] + 1
        optimizer.load_state_dict(state['optimizer_state_dict'])
        global_step = state['global_step']
    else:
        print('No model to preload, starting from scratch')

    loss_fn = nn.CrossEntropyLoss(ignore_index=tokenizer_src.token_to_id('[PAD]'), label_smoothing=0.1).to(device)

    total_loss = 0  # Initialize total loss accumulator
    num_batches = 0  # Initialize batch counter

    epoch = current_epoch
    print(f"Epoch {epoch}: Training with causal mask with future")
    model_causal_mask_with_future.train()
    batch_iterator = tqdm(train_dataloader, desc=f"Epoch {epoch:02d} - Training with causal mask with future")
    for batch in batch_iterator:
        encoder_input = batch['encoder_input'].to(device)
        decoder_input = batch['decoder_input'].to(device)
        encoder_mask = batch['encoder_mask'].to(device)
        decoder_mask = batch['decoder_mask_with_future'].to(device)

        encoder_output = model_causal_mask_with_future.encode(encoder_input, encoder_mask)
        decoder_output = model_causal_mask_with_future.decode(encoder_output, encoder_mask, decoder_input, decoder_mask)
        proj_output = model_causal_mask.project(decoder_output)

        label = batch['label'].to(device)

        loss = loss_fn(proj_output.view(-1, tokenizer_tgt.get_vocab_size()), label.view(-1))
        batch_iterator.set_postfix({"loss": f"{loss.item():6.3f}"})

        writer.add_scalar('train loss/causal_mask_with_future', loss.item(), global_step)
        writer.flush()

        loss.backward()

        
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)

        total_loss += loss.item()  # Accumulate loss
        num_batches += 1  # Increment batch counter

        global_step += 1

    average_loss = total_loss / num_batches  # Compute average loss    
    if epoch == num_epochs - 1:
        validate_train_model_whole(model_causal_mask, model_causal_mask_with_future, val_dataloader, tokenizer_src, tokenizer_tgt, config['seq_len'], device, lambda msg: batch_iterator.write(msg), global_step, writer)

    model_filename = get_weights_file_path(config, f"causal_mask_with_future_epoch_{epoch:02d}")
    torch.save({
            'epoch': epoch,
            'model_state_dict': model_causal_mask_with_future.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'global_step': global_step
        }, model_filename)

    return model_causal_mask_with_future, average_loss 

def alternate_training(config, num_epochs):

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    train_dataloader, val_dataloader, tokenizer_src, tokenizer_tgt = get_ds(config)

    model_causal_mask = get_model(config, tokenizer_src.get_vocab_size(), tokenizer_tgt.get_vocab_size()).to(device)
    model_causal_mask_with_future = get_model(config, tokenizer_src.get_vocab_size(), tokenizer_tgt.get_vocab_size()).to(device)

    losses_causal_mask = []
    losses_causal_mask_with_future = []
    
    for epoch in range(num_epochs):
        print(f"Starting Epoch {epoch+1}/{num_epochs}")

        print(f"Training epoch {epoch+1} with causal mask")
        model_causal_mask, loss_causal_mask = train_model_causal_mask(config, epoch, model_causal_mask, device,num_epochs )
        losses_causal_mask.append(loss_causal_mask)

        print(f"Training epoch {epoch+1} with causal mask and future context")
        model_causal_mask_with_future, loss_causal_mask_with_future = train_model_causal_mask_with_future(config, epoch, model_causal_mask, model_causal_mask_with_future, device,num_epochs)
        losses_causal_mask_with_future.append(loss_causal_mask_with_future)

        print(f"Completed Epoch {epoch+1}/{num_epochs}")

    return losses_causal_mask, losses_causal_mask_with_future

if __name__ == '__main__':
    warnings.filterwarnings("ignore")
    config = get_config()
    num_epochs = config['num_epochs']
    losses_causal_mask, losses_causal_mask_with_future = alternate_training(config, num_epochs)

