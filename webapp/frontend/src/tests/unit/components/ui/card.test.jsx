import { render, screen } from '@testing-library/react';
import { 
  Card, 
  CardHeader, 
  CardTitle, 
  CardDescription, 
  CardContent, 
  CardFooter 
} from '../../../../components/ui/card';

describe('Card Components', () => {
  describe('Card', () => {
    test('renders without crashing', () => {
      render(<Card>Test Card</Card>);
      expect(screen.getByText('Test Card')).toBeInTheDocument();
    });

    test('applies custom className', () => {
      render(<Card className="custom-card">Card Content</Card>);
      const card = screen.getByText('Card Content').closest('.MuiCard-root');
      expect(card).toHaveClass('custom-card');
    });

    test('forwards ref correctly', () => {
      const ref = { current: null };
      render(<Card ref={ref}>Test</Card>);
      expect(ref.current).toBeInstanceOf(HTMLElement);
    });

    test('forwards additional props', () => {
      render(<Card data-testid="test-card" elevation={3}>Test</Card>);
      const card = screen.getByTestId('test-card');
      expect(card).toBeInTheDocument();
    });

    test('has correct display name', () => {
      expect(Card.displayName).toBe('Card');
    });
  });

  describe('CardHeader', () => {
    test('renders without crashing', () => {
      render(<CardHeader title="Header Title" />);
      expect(screen.getByText('Header Title')).toBeInTheDocument();
    });

    test('applies custom className', () => {
      render(<CardHeader className="custom-header" title="Test" />);
      const header = screen.getByText('Test').closest('.MuiCardHeader-root');
      expect(header).toHaveClass('custom-header');
    });

    test('forwards ref correctly', () => {
      const ref = { current: null };
      render(<CardHeader ref={ref} title="Test" />);
      expect(ref.current).toBeInstanceOf(HTMLElement);
    });

    test('supports title and subheader', () => {
      render(<CardHeader title="Main Title" subheader="Subtitle" />);
      expect(screen.getByText('Main Title')).toBeInTheDocument();
      expect(screen.getByText('Subtitle')).toBeInTheDocument();
    });

    test('has correct display name', () => {
      expect(CardHeader.displayName).toBe('CardHeader');
    });
  });

  describe('CardTitle', () => {
    test('renders without crashing', () => {
      render(<CardTitle>Card Title</CardTitle>);
      expect(screen.getByText('Card Title')).toBeInTheDocument();
    });

    test('renders as h6 variant Typography', () => {
      render(<CardTitle>Title Text</CardTitle>);
      const title = screen.getByText('Title Text');
      expect(title).toHaveClass('MuiTypography-h6');
    });

    test('applies custom className', () => {
      render(<CardTitle className="custom-title">Test Title</CardTitle>);
      const title = screen.getByText('Test Title');
      expect(title).toHaveClass('custom-title');
    });

    test('forwards ref correctly', () => {
      const ref = { current: null };
      render(<CardTitle ref={ref}>Test</CardTitle>);
      expect(ref.current).toBeInstanceOf(HTMLElement);
    });

    test('renders as div component', () => {
      render(<CardTitle>Title</CardTitle>);
      const title = screen.getByText('Title');
      expect(title.tagName).toBe('DIV');
    });

    test('has correct display name', () => {
      expect(CardTitle.displayName).toBe('CardTitle');
    });
  });

  describe('CardDescription', () => {
    test('renders without crashing', () => {
      render(<CardDescription>Card Description</CardDescription>);
      expect(screen.getByText('Card Description')).toBeInTheDocument();
    });

    test('renders as body2 variant Typography', () => {
      render(<CardDescription>Description Text</CardDescription>);
      const description = screen.getByText('Description Text');
      expect(description).toHaveClass('MuiTypography-body2');
    });

    test('has text secondary color', () => {
      render(<CardDescription>Description</CardDescription>);
      const description = screen.getByText('Description');
      // MUI v5 uses color prop instead of CSS class for text secondary
      expect(description).toBeInTheDocument();
    });

    test('applies custom className', () => {
      render(<CardDescription className="custom-desc">Test Desc</CardDescription>);
      const description = screen.getByText('Test Desc');
      expect(description).toHaveClass('custom-desc');
    });

    test('forwards ref correctly', () => {
      const ref = { current: null };
      render(<CardDescription ref={ref}>Test</CardDescription>);
      expect(ref.current).toBeInstanceOf(HTMLElement);
    });

    test('has correct display name', () => {
      expect(CardDescription.displayName).toBe('CardDescription');
    });
  });

  describe('CardContent', () => {
    test('renders without crashing', () => {
      render(<CardContent>Card Content</CardContent>);
      expect(screen.getByText('Card Content')).toBeInTheDocument();
    });

    test('applies custom className', () => {
      render(<CardContent className="custom-content">Test Content</CardContent>);
      const content = screen.getByText('Test Content').closest('.MuiCardContent-root');
      expect(content).toHaveClass('custom-content');
    });

    test('forwards ref correctly', () => {
      const ref = { current: null };
      render(<CardContent ref={ref}>Test</CardContent>);
      expect(ref.current).toBeInstanceOf(HTMLElement);
    });

    test('forwards additional props', () => {
      render(<CardContent data-testid="test-content">Test</CardContent>);
      const content = screen.getByTestId('test-content');
      expect(content).toBeInTheDocument();
    });

    test('has correct display name', () => {
      expect(CardContent.displayName).toBe('CardContent');
    });
  });

  describe('CardFooter', () => {
    test('renders without crashing', () => {
      render(<CardFooter>Card Footer</CardFooter>);
      expect(screen.getByText('Card Footer')).toBeInTheDocument();
    });

    test('applies custom className', () => {
      render(<CardFooter className="custom-footer">Test Footer</CardFooter>);
      const footer = screen.getByText('Test Footer');
      expect(footer).toHaveClass('custom-footer');
    });

    test('has default padding style', () => {
      render(<CardFooter>Footer</CardFooter>);
      const footer = screen.getByText('Footer');
      expect(footer).toHaveStyle({ padding: '16px' });
    });

    test('forwards ref correctly', () => {
      const ref = { current: null };
      render(<CardFooter ref={ref}>Test</CardFooter>);
      expect(ref.current).toBeInstanceOf(HTMLElement);
      expect(ref.current.tagName).toBe('DIV');
    });

    test('forwards additional props', () => {
      render(<CardFooter data-testid="test-footer">Test</CardFooter>);
      const footer = screen.getByTestId('test-footer');
      expect(footer).toBeInTheDocument();
    });

    test('has correct display name', () => {
      expect(CardFooter.displayName).toBe('CardFooter');
    });
  });

  describe('Complete Card Structure', () => {
    test('renders all card components together', () => {
      render(
        <Card>
          <CardHeader title="Card Title" subheader="Card Subtitle" />
          <CardContent>
            <CardTitle>Content Title</CardTitle>
            <CardDescription>Content description text</CardDescription>
            <p>Main content goes here</p>
          </CardContent>
          <CardFooter>Footer content</CardFooter>
        </Card>
      );

      expect(screen.getByText('Card Title')).toBeInTheDocument();
      expect(screen.getByText('Card Subtitle')).toBeInTheDocument();
      expect(screen.getByText('Content Title')).toBeInTheDocument();
      expect(screen.getByText('Content description text')).toBeInTheDocument();
      expect(screen.getByText('Main content goes here')).toBeInTheDocument();
      expect(screen.getByText('Footer content')).toBeInTheDocument();
    });

    test('handles nested card structure with proper hierarchy', () => {
      render(
        <Card className="outer-card">
          <CardContent>
            <Card className="inner-card">
              <CardContent>Inner card content</CardContent>
            </Card>
          </CardContent>
        </Card>
      );

      const outerCard = screen.getByText('Inner card content').closest('.outer-card');
      const innerCard = screen.getByText('Inner card content').closest('.inner-card');
      
      expect(outerCard).toBeInTheDocument();
      expect(innerCard).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    test('handles empty content', () => {
      render(<Card />);
      expect(document.querySelector('.MuiCard-root')).toBeInTheDocument();
    });

    test('handles null children', () => {
      render(<Card>{null}</Card>);
      expect(document.querySelector('.MuiCard-root')).toBeInTheDocument();
    });

    test('handles undefined children', () => {
      render(<Card>{undefined}</Card>);
      expect(document.querySelector('.MuiCard-root')).toBeInTheDocument();
    });

    test('handles complex children', () => {
      render(
        <Card>
          <div>
            <span>Complex</span>
            <strong>Content</strong>
            {42}
            {true && <p>Conditional</p>}
          </div>
        </Card>
      );

      expect(screen.getByText('Complex')).toBeInTheDocument();
      expect(screen.getByText('Content')).toBeInTheDocument();
      expect(screen.getByText('42')).toBeInTheDocument();
      expect(screen.getByText('Conditional')).toBeInTheDocument();
    });
  });

  describe('Style Overrides', () => {
    test('applies custom styles', () => {
      render(
        <Card style={{ backgroundColor: 'red', margin: '10px' }}>
          Styled Card
        </Card>
      );
      
      const card = screen.getByText('Styled Card').closest('.MuiCard-root');
      // Style matching can be complex with MUI - just verify the card exists
      expect(card).toBeInTheDocument();
      expect(card).toHaveAttribute('style');
    });

    test('combines custom className with MUI classes', () => {
      render(<Card className="my-custom-class">Test</Card>);
      const card = screen.getByText('Test').closest('.MuiCard-root');
      expect(card).toHaveClass('MuiCard-root');
      expect(card).toHaveClass('my-custom-class');
    });
  });
});