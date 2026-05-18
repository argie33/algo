import React from 'react';
import { Box, Card, CardContent, Skeleton, Stack, Grid } from '@mui/material';

/**
 * SkeletonCard - Placeholder while loading data.
 * Shows animated skeleton matching expected content structure.
 */
export function SkeletonCard({ rows = 3 }) {
  return (
    <Card>
      <CardContent>
        <Stack spacing={2}>
          {Array.from({ length: rows }).map((_, i) => (
            <Skeleton key={i} variant="text" height={40} />
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}

/**
 * GridSkeleton - Multiple cards for grid layouts.
 */
export function GridSkeleton({ count = 4 }) {
  return (
    <Grid container spacing={2}>
      {Array.from({ length: count }).map((_, i) => (
        <Grid item xs={12} sm={6} md={3} key={i}>
          <SkeletonCard rows={2} />
        </Grid>
      ))}
    </Grid>
  );
}

/**
 * TableSkeleton - Placeholder for table data.
 */
export function TableSkeleton({ rows = 5, columns = 5 }) {
  return (
    <Box>
      {Array.from({ length: rows }).map((_, i) => (
        <Stack key={i} direction="row" spacing={1} sx={{ mb: 1 }}>
          {Array.from({ length: columns }).map((_, j) => (
            <Skeleton
              key={j}
              variant="text"
              height={40}
              sx={{ flex: 1 }}
            />
          ))}
        </Stack>
      ))}
    </Box>
  );
}

export default SkeletonCard;
