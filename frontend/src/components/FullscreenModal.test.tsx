import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import FullscreenModal from './FullscreenModal';

describe('FullscreenModal', () => {
  it('renders children content', () => {
    render(
      <FullscreenModal onClose={vi.fn()}>
        <p>Card content</p>
      </FullscreenModal>,
    );

    expect(screen.getByText('Card content')).toBeInTheDocument();
  });

  it('renders as a fixed fullscreen overlay with z-50', () => {
    render(
      <FullscreenModal onClose={vi.fn()}>
        <p>Content</p>
      </FullscreenModal>,
    );

    const modal = screen.getByTestId('fullscreen-modal');
    expect(modal).toHaveClass('fixed', 'inset-0', 'z-50');
  });

  it('has a visible close button', () => {
    render(
      <FullscreenModal onClose={vi.fn()}>
        <p>Content</p>
      </FullscreenModal>,
    );

    const closeBtn = screen.getByTestId('fullscreen-modal-close');
    expect(closeBtn).toBeInTheDocument();
    expect(closeBtn).toHaveAttribute('aria-label', 'Close fullscreen');
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn();
    render(
      <FullscreenModal onClose={onClose}>
        <p>Content</p>
      </FullscreenModal>,
    );

    const closeBtn = screen.getByTestId('fullscreen-modal-close');
    fireEvent.click(closeBtn);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when Escape key is pressed', () => {
    const onClose = vi.fn();
    render(
      <FullscreenModal onClose={onClose}>
        <p>Content</p>
      </FullscreenModal>,
    );

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not call onClose for non-Escape keys', () => {
    const onClose = vi.fn();
    render(
      <FullscreenModal onClose={onClose}>
        <p>Content</p>
      </FullscreenModal>,
    );

    fireEvent.keyDown(document, { key: 'Enter' });
    fireEvent.keyDown(document, { key: 'a' });

    expect(onClose).not.toHaveBeenCalled();
  });

  it('has role="dialog" and aria-modal for accessibility', () => {
    render(
      <FullscreenModal onClose={vi.fn()}>
        <p>Content</p>
      </FullscreenModal>,
    );

    const modal = screen.getByRole('dialog');
    expect(modal).toHaveAttribute('aria-modal', 'true');
  });
});
