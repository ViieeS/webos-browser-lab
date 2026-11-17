/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */
/* The DMA_BUF_IOCTL_SYNC part of Linux's uapi <linux/dma-buf.h> (4.6+). The sysroot carries 4.4
 * headers to match the TV kernel, which predate this file; WebKit's GBM buffer mapping includes it.
 * On the TV the ioctl fails with ENOTTY, which only matters for GBM-backed buffers (none here). */
#ifndef _DMA_BUF_UAPI_H_
#define _DMA_BUF_UAPI_H_
#include <linux/types.h>
struct dma_buf_sync {
	__u64 flags;
};
#define DMA_BUF_SYNC_READ      (1 << 0)
#define DMA_BUF_SYNC_WRITE     (2 << 0)
#define DMA_BUF_SYNC_RW        (DMA_BUF_SYNC_READ | DMA_BUF_SYNC_WRITE)
#define DMA_BUF_SYNC_START     (0 << 2)
#define DMA_BUF_SYNC_END       (1 << 2)
#define DMA_BUF_SYNC_VALID_FLAGS_MASK (DMA_BUF_SYNC_RW | DMA_BUF_SYNC_END)
#define DMA_BUF_BASE		'b'
#define DMA_BUF_IOCTL_SYNC	_IOW(DMA_BUF_BASE, 0, struct dma_buf_sync)
#endif
