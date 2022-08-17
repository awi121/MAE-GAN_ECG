import os
import json
from pathlib import Path
import torch
torch.cuda.empty_cache()

from pytorch_lightning import Trainer, seed_everything
from pytorch_lightning.callbacks import LearningRateMonitor
from pytorch_lightning.loggers import WandbLogger
from pytorch_lightning.callbacks.early_stopping import EarlyStopping

from model.transfer_model import TransferModel
from utils.checkpointer import Checkpointer
from setup import parse_args_pretrain, METHODS, NUM_CLASSES, BACKBONES, TARGET_TYPE

from data.datamodule import ECGDataModule

import logging 
logging.basicConfig(level=logging.NOTSET)


def main():
    args = parse_args_pretrain()
    seed_everything(args.seed)

    console_log = logging.getLogger("Lightning")
    console_log.info(" Beginning pretrain main() with seed {} and arguments {}: \n".format(args.seed, args))

    callbacks = []

    encoder = BACKBONES[args.encoder_name](**vars(args))

    MethodClass = METHODS[args.method]
    model = MethodClass(encoder=encoder, 
                        console_log=console_log, 
                        n_classes=NUM_CLASSES[args.dataset], 
                        target_type=TARGET_TYPE[args.dataset], 
                        **args.__dict__)
                        
    console_log.info(" Loaded {} model.".format(args.method))

    data_module= ECGDataModule(data_dir=args.data_dir, 
                               dataset=args.dataset, 
                               batch_size=args.batch_size, 
                               method=args.method, 
                               seed=args.seed, 
                               positive_pairing=args.positive_pairing,
                               nleads=12, 
                               num_workers=args.num_workers, 
                               do_test=False,
                               debug=args.debug)

    console_log.info(" Loaded datamodule with dataset {}.".format(args.dataset))

    callbacks = []
    early_stop = EarlyStopping(monitor="val_loss", mode="min", patience=10)
    callbacks.append(early_stop)

    # wandb logging
    if args.wandb:
        console_log.info("Initiating WandB configs.")
        wandb_logger = WandbLogger(
            name=args.name, project=args.project, entity=args.entity, offline=True
        )
        wandb_logger.watch(model, log=None) #, log_freq=100)
        wandb_logger.log_hyperparams(args)

        # lr logging
        lr_monitor = LearningRateMonitor(logging_interval="epoch")
        callbacks.append(lr_monitor)

        # save checkpoint on last epoch only
        ckpt = Checkpointer(
            args,
            logdir=os.path.join(args.checkpoint_dir, args.name, "seed{}".format(args.seed)),
            frequency=args.checkpoint_frequency,
        )
        callbacks.append(ckpt)

    trainer = Trainer.from_argparse_args(
        args,
        logger=wandb_logger if args.wandb else None,
        callbacks=callbacks,
        checkpoint_callback=False,
        terminate_on_nan=True,
        # accelerator="gpu", 
        gpus=args.num_devices,
        fast_dev_run=args.debug,
        accelerator="ddp"
    )
    console_log.info(" Created Lightning Trainer and starting training.")

    trainer.fit(model=model, datamodule=data_module)


if __name__ == "__main__":
    main()



