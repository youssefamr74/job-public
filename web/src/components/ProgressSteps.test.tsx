import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ProgressSteps } from './ProgressSteps';

describe('ProgressSteps', () => {
  it.each([
    [1, 'Reached Applied, step 1 of 4', 1],
    [3, 'Reached Interview, step 3 of 4', 3],
    [4, 'Reached Offer, step 4 of 4', 4],
  ])('marks %i reached step(s)', (step, label, reached) => {
    const { container } = render(<ProgressSteps step={step} />);
    expect(screen.getByRole('img', { name: label })).toBeInTheDocument();
    expect(container.querySelectorAll('[data-reached]')).toHaveLength(reached);
  });
});
