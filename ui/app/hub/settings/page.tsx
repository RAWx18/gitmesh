"use client";

import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { 
  User, 
  Shield, 
  Github,
  Trash2,
  Plus,
  Copy,
  Check,
  X,
  KeyRound,
  AppWindow,
  CreditCard,
  DollarSign,
  FileText,
  ChevronRight,
  Settings,
  Crown,
  Zap,
  Building,
  Star,
  Calendar,
  Eye,
  EyeOff,
  ExternalLink,
  AlertCircle,
  CheckCircle
} from 'lucide-react';

// Plan definitions with detailed features
const PLANS = [
  {
    id: 'free',
    name: 'Free Community',
    price: 0,
    description: 'Perfect for individuals and small open-source projects',
    features: ['5 repositories', 'Basic analytics', 'Community support', 'Standard security'],
    icon: <Star className="w-5 h-5" />,
    badge: null
  },
  {
    id: 'contributor',
    name: 'Contributor Pro',
    price: 9,
    description: 'For dedicated contributors and power users',
    features: ['25 repositories', 'Advanced analytics', 'Priority support', 'Enhanced security', 'API access'],
    icon: <Zap className="w-5 h-5" />,
    badge: 'Popular'
  },
  {
    id: 'maintainer',
    name: 'Maintainer Pro',
    price: 29,
    description: 'For project maintainers and team leads',
    features: ['100 repositories', 'Team collaboration', '24/7 support', 'Advanced security', 'Full API access', 'Custom integrations'],
    icon: <Crown className="w-5 h-5" />,
    badge: 'Recommended'
  },
  {
    id: 'team',
    name: 'Team Enterprise',
    price: 75,
    description: 'For professional teams and organizations',
    features: ['Unlimited repositories', 'Advanced team features', 'Dedicated support', 'Enterprise security', 'Custom solutions', 'SLA guarantee'],
    icon: <Building className="w-5 h-5" />,
    badge: null
  },
  {
    id: 'enterprise',
    name: 'Enterprise Plus',
    price: 149,
    description: 'For large organizations with custom needs',
    features: ['Everything in Team', 'Custom deployment', 'Advanced compliance', 'Dedicated account manager', 'Custom training', 'Priority feature requests'],
    icon: <Shield className="w-5 h-5" />,
    badge: null
  }
];

type SettingsTab = 'profile' | 'subscription' | 'security' | 'integrations' | 'billing';

export default function ProductionSettings() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('profile');
  const [currentPlan, setCurrentPlan] = useState('maintainer'); // This should fetch from /backend/.env TIER_PLAN
  const [apiKeys, setApiKeys] = useState([]);
  const [connectedApps, setConnectedApps] = useState([]);
  const [billingHistory, setBillingHistory] = useState([]);
  const [paymentMethods, setPaymentMethods] = useState([]);
  const [showApiKey, setShowApiKey] = useState({});

  // Mock user data - in production this would come from auth context
  const user = {
    name: 'full name',
    login: 'username',
    email: '@gitmesh.dev',
    avatar_url: '',
    joinDate: '2023-01-15'
  };

  useEffect(() => {
    // Fetch current plan from backend
    // fetch('/api/user/plan').then(res => res.json()).then(data => setCurrentPlan(data.tier))
    
    // Load other data
    loadUserData();
  }, []);

  const loadUserData = async () => {
    // In production, these would be actual API calls
    // const [keys, apps, billing, payments] = await Promise.all([
    //   fetch('/api/user/api-keys').then(r => r.json()),
    //   fetch('/api/user/connected-apps').then(r => r.json()),
    //   fetch('/api/user/billing-history').then(r => r.json()),
    //   fetch('/api/user/payment-methods').then(r => r.json())
    // ]);
    
    // setApiKeys(keys);
    // setConnectedApps(apps);
    // setBillingHistory(billing);
    // setPaymentMethods(payments);
  };

  const SIDEBAR_TABS = [
    { id: 'profile', name: 'Profile', icon: <User className="w-5 h-5" /> },
    { id: 'subscription', name: 'Subscription', icon: <Crown className="w-5 h-5" /> },
    { id: 'security', name: 'Security', icon: <Shield className="w-5 h-5" /> },
    { id: 'integrations', name: 'Integrations', icon: <AppWindow className="w-5 h-5" /> },
    { id: 'billing', name: 'Billing', icon: <CreditCard className="w-5 h-5" /> },
  ];

  const currentPlanData = PLANS.find(p => p.id === currentPlan);

  return (
    <div className="min-h-screen bg-black ">
      <div className="container mx-auto px-6 py-12 max-w-7xl">
        {/* Header */}
        <div className="mb-12">
          <div className="flex items-center gap-3 mb-4">
            <div>
              <h1 className="text-4xl font-bold tracking-tight">Settings</h1>
              <p className="text-lg text-muted-foreground">
                Manage your account, subscriptions, and integrations
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-12 gap-8">
          {/* Sidebar Navigation */}
          <aside className="col-span-12 lg:col-span-3">
            <Card className="sticky top-6">
              <CardContent className="p-2">
                <nav className="space-y-1">
                  {SIDEBAR_TABS.map((tab) => (
                    <Button
                      key={tab.id}
                      variant={activeTab === tab.id ? 'secondary' : 'ghost'}
                      className={`w-full justify-start text-left p-4 h-auto ${
                        activeTab === tab.id 
                          ? 'bg-primary/10 text-primary border-primary/20 shadow-sm' 
                          : 'hover:bg-muted/50'
                      }`}
                      onClick={() => setActiveTab(tab.id)}
                    >
                      <div className="flex items-center gap-3">
                        {tab.icon}
                        <span className="font-medium">{tab.name}</span>
                      </div>
                      {activeTab === tab.id && (
                        <ChevronRight className="w-4 h-4 ml-auto" />
                      )}
                    </Button>
                  ))}
                </nav>
              </CardContent>
            </Card>
          </aside>

          {/* Main Content */}
          <main className="col-span-12 lg:col-span-9">
            {activeTab === 'profile' && <ProfileSection user={user} />}
            {activeTab === 'subscription' && <SubscriptionSection currentPlan={currentPlanData} />}
            {activeTab === 'security' && <SecuritySection />}
            {activeTab === 'integrations' && <IntegrationsSection />}
            {activeTab === 'billing' && <BillingSection />}
          </main>
        </div>
      </div>
    </div>
  );
}

// Profile Section
const ProfileSection = ({ user }) => (
  <div className="space-y-8">
    <Card className="border-0 shadow-lg">
      <CardHeader className="pb-8">
        <CardTitle className="text-2xl">Profile Information</CardTitle>
        <CardDescription className="text-base">
          This information will be displayed publicly on your GitMesh profile
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-8">
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-6">
          <Avatar className="w-24 h-24 border-4 border-background shadow-lg">
            <AvatarImage src={user?.avatar_url} />
            <AvatarFallback className="text-2xl font-semibold bg-primary/10 text-primary">
              {user?.name?.charAt(0) || 'U'}
            </AvatarFallback>
          </Avatar>
          <div className="space-y-2">
            <Button variant="outline" size="lg">
              <Plus className="w-4 h-4 mr-2" />
              Upload New Avatar
            </Button>
            <p className="text-sm text-muted-foreground">
              JPG, GIF or PNG. Max size of 800K
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <Label htmlFor="display-name" className="text-base font-medium">Display Name</Label>
            <Input 
              id="display-name" 
              defaultValue={user?.name || ''} 
              className="h-12 text-base"
            />
            <p className="text-sm text-muted-foreground">
              Your full name or preferred display name
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="username" className="text-base font-medium">Username</Label>
            <Input 
              id="username" 
              defaultValue={user?.login || ''} 
              disabled 
              className="h-12 text-base bg-muted/50"
            />
            <p className="text-sm text-muted-foreground">
              Synced from GitHub, cannot be changed
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="email" className="text-base font-medium">Email</Label>
            <Input 
              id="email" 
              defaultValue={user?.email || ''} 
              type="email"
              className="h-12 text-base"
            />
            <p className="text-sm text-muted-foreground">
              Used for notifications and account recovery
            </p>
          </div>
          <div className="space-y-2">
            <Label className="text-base font-medium">Member Since</Label>
            <div className="flex items-center gap-2 h-12 px-3 py-2 bg-muted/50 rounded-md">
              <Calendar className="w-4 h-4 text-muted-foreground" />
              <span className="text-base">{user?.joinDate}</span>
            </div>
          </div>
        </div>

        <div className="flex justify-end pt-4">
          <Button size="lg" className="px-8">
            <Check className="w-4 h-4 mr-2" />
            Save Changes
          </Button>
        </div>
      </CardContent>
    </Card>
  </div>
);

// Subscription Section
const SubscriptionSection = ({ currentPlan }) => (
  <div className="space-y-8">
    {/* Current Plan */}
    <Card className="border-0 shadow-lg">
      <CardHeader className="pb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-lg">
              {currentPlan?.icon}
            </div>
            <div>
              <CardTitle className="text-2xl">Current Plan</CardTitle>
              <CardDescription className="text-base">
                You're currently on <span className="font-semibold text-primary">{currentPlan?.name}</span>
              </CardDescription>
            </div>
          </div>
          <div className="text-right">
            <div className="text-4xl font-bold">${currentPlan?.price}</div>
            <div className="text-muted-foreground">/month</div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="bg-muted/30 p-6 rounded-lg">
          <p className="text-base mb-4">{currentPlan?.description}</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {currentPlan?.features.map((feature, index) => (
              <div key={index} className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-green-600" />
                <span className="text-sm">{feature}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <p className="text-sm text-blue-800">
            Your plan renews on October 1, 2025. You can upgrade, downgrade, or cancel at any time.
          </p>
        </div>
      </CardContent>
    </Card>

    {/* Available Plans */}
    <Card className="border-0 shadow-lg">
      <CardHeader>
        <CardTitle className="text-2xl">Available Plans</CardTitle>
        <CardDescription className="text-base">
          Choose the plan that best fits your needs
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {PLANS.filter(plan => plan.id !== currentPlan?.id).map((plan) => (
            <div 
              key={plan.id}
              className="relative p-6 border-2 border-border rounded-xl hover:border-primary/50 transition-all duration-200 hover:shadow-md"
            >
              {plan.badge && (
                <Badge className="absolute -top-2 left-4 bg-primary text-primary-foreground">
                  {plan.badge}
                </Badge>
              )}
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-primary/10 rounded-lg">
                  {plan.icon}
                </div>
                <div>
                  <h3 className="text-xl font-semibold">{plan.name}</h3>
                  <p className="text-muted-foreground">{plan.description}</p>
                </div>
              </div>
              
              <div className="mb-4">
                <div className="text-3xl font-bold">${plan.price}<span className="text-lg font-normal text-muted-foreground">/mo</span></div>
              </div>

              <div className="space-y-2 mb-6">
                {plan.features.slice(0, 4).map((feature, index) => (
                  <div key={index} className="flex items-center gap-2 text-sm">
                    <CheckCircle className="w-4 h-4 text-green-600" />
                    <span>{feature}</span>
                  </div>
                ))}
              </div>

              <Button 
                className="w-full" 
                variant={plan.price > currentPlan?.price ? 'default' : 'outline'}
              >
                {plan.price > currentPlan?.price ? 'Upgrade' : 'Downgrade'} to {plan.name}
              </Button>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  </div>
);

// Security Section
const SecuritySection = () => {
  const [apiKeys, setApiKeys] = useState([]);
  const [showKey, setShowKey] = useState({});

  return (
    <div className="space-y-8">
      {/* API Keys */}
      <Card className="border-0 shadow-lg">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-2xl flex items-center gap-3">
                <KeyRound className="w-6 h-6" />
                API Keys
              </CardTitle>
              <CardDescription className="text-base">
                Manage your API keys for integrations and automation
              </CardDescription>
            </div>
            <Dialog>
              <DialogTrigger asChild>
                <Button size="lg">
                  <Plus className="w-4 h-4 mr-2" />
                  Generate New Key
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-md">
                <DialogHeader>
                  <DialogTitle>Generate API Key</DialogTitle>
                  <DialogDescription>
                    Create a new API key with specific permissions
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-6 py-4">
                  <div className="space-y-2">
                    <Label htmlFor="key-name">Key Name</Label>
                    <Input 
                      id="key-name" 
                      placeholder="e.g., CI/CD Pipeline"
                      className="h-12"
                    />
                  </div>
                  <div className="space-y-4">
                    <Label>Permissions</Label>
                    <div className="space-y-4 p-4 border rounded-lg bg-muted/20">
                      <div className="flex items-center justify-between">
                        <div>
                          <Label htmlFor="perm-read" className="font-medium">Read Access</Label>
                          <p className="text-sm text-muted-foreground">View repositories and data</p>
                        </div>
                        <Switch id="perm-read" defaultChecked />
                      </div>
                      <div className="flex items-center justify-between">
                        <div>
                          <Label htmlFor="perm-write" className="font-medium">Write Access</Label>
                          <p className="text-sm text-muted-foreground">Modify repositories and data</p>
                        </div>
                        <Switch id="perm-write" />
                      </div>
                      <div className="flex items-center justify-between">
                        <div>
                          <Label htmlFor="perm-admin" className="font-medium">Admin Access</Label>
                          <p className="text-sm text-muted-foreground">Full administrative privileges</p>
                        </div>
                        <Switch id="perm-admin" />
                      </div>
                    </div>
                  </div>
                </div>
                <DialogFooter>
                  <Button className="w-full" size="lg">Generate Key</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </CardHeader>
        <CardContent>
          {apiKeys.length === 0 ? (
            <div className="text-center py-12">
              <KeyRound className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">No API Keys</h3>
              <p className="text-muted-foreground mb-4">
                You haven't generated any API keys yet
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {apiKeys.map((key) => (
                <div key={key.id} className="flex items-center justify-between p-4 border rounded-lg">
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <h3 className="font-semibold">{key.name}</h3>
                      <Badge variant="outline">{key.permissions}</Badge>
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <code className="text-sm bg-muted px-2 py-1 rounded">
                        {showKey[key.id] ? key.value : key.maskedValue}
                      </code>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setShowKey(prev => ({ ...prev, [key.id]: !prev[key.id] }))}
                      >
                        {showKey[key.id] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </Button>
                      <Button variant="ghost" size="sm">
                        <Copy className="w-4 h-4" />
                      </Button>
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                      Last used: {key.lastUsed}
                    </p>
                  </div>
                  <Button variant="ghost" size="sm" className="text-red-600 hover:text-red-700">
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Two Factor Authentication */}
      <Card className="border-0 shadow-lg">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center gap-3">
            <Shield className="w-6 h-6" />
            Two-Factor Authentication
          </CardTitle>
          <CardDescription className="text-base">
            Add an extra layer of security to your account
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between p-4 border rounded-lg">
            <div>
              <h3 className="font-semibold">Authenticator App</h3>
              <p className="text-sm text-muted-foreground">
                Use an app like Google Authenticator or Authy
              </p>
            </div>
            <Button variant="outline">Enable 2FA</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// Integrations Section
const IntegrationsSection = () => {
  const [connectedApps, setConnectedApps] = useState([]);

  return (
    <div className="space-y-8">
      <Card className="border-0 shadow-lg">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center gap-3">
            <AppWindow className="w-6 h-6" />
            Connected Applications
          </CardTitle>
          <CardDescription className="text-base">
            Manage third-party applications connected to your account
          </CardDescription>
        </CardHeader>
        <CardContent>
          {connectedApps.length === 0 ? (
            <div className="text-center py-12">
              <AppWindow className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">No Connected Apps</h3>
              <p className="text-muted-foreground mb-4">
                You haven't connected any third-party applications yet
              </p>
              <Button>
                <Plus className="w-4 h-4 mr-2" />
                Browse Integrations
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {connectedApps.map((app) => (
                <div key={app.id} className="flex items-center justify-between p-4 border rounded-lg">
                  <div className="flex items-center gap-4">
                    <Avatar>
                      <AvatarImage src={app.icon} />
                      <AvatarFallback>{app.name.charAt(0)}</AvatarFallback>
                    </Avatar>
                    <div>
                      <h3 className="font-semibold">{app.name}</h3>
                      <p className="text-sm text-muted-foreground">{app.description}</p>
                      <p className="text-xs text-muted-foreground">
                        Connected on {app.connectedDate}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm">
                      Configure
                    </Button>
                    <Button variant="ghost" size="sm" className="text-red-600">
                      Disconnect
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

// Billing Section
const BillingSection = () => {
  const [paymentMethods, setPaymentMethods] = useState([]);
  const [billingHistory, setBillingHistory] = useState([]);

  return (
    <div className="space-y-8">
      {/* Payment Methods */}
      <Card className="border-0 shadow-lg">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-2xl flex items-center gap-3">
                <CreditCard className="w-6 h-6" />
                Payment Methods
              </CardTitle>
              <CardDescription className="text-base">
                Manage your payment methods and billing information
              </CardDescription>
            </div>
            <Dialog>
              <DialogTrigger asChild>
                <Button size="lg">
                  <Plus className="w-4 h-4 mr-2" />
                  Add Payment Method
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-md">
                <DialogHeader>
                  <DialogTitle>Add Payment Method</DialogTitle>
                  <DialogDescription>
                    Choose your preferred payment method
                  </DialogDescription>
                </DialogHeader>
                <Tabs defaultValue="card" className="py-4">
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="card">Credit Card</TabsTrigger>
                    <TabsTrigger value="razorpay">Razorpay</TabsTrigger>
                  </TabsList>
                  <TabsContent value="card" className="space-y-4">
                    <div className="space-y-2">
                      <Label htmlFor="card-number">Card Number</Label>
                      <Input id="card-number" placeholder="1234 5678 9012 3456" />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="expiry">Expiry Date</Label>
                        <Input id="expiry" placeholder="MM/YY" />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="cvv">CVV</Label>
                        <Input id="cvv" placeholder="123" />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="cardholder">Cardholder Name</Label>
                      <Input id="cardholder" placeholder="John Doe" />
                    </div>
                  </TabsContent>
                  <TabsContent value="razorpay" className="space-y-4">
                    <div className="text-center py-8">
                      <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                        <CreditCard className="w-8 h-8 text-blue-600" />
                      </div>
                      <h3 className="font-semibold mb-2">Razorpay Gateway</h3>
                      <p className="text-sm text-muted-foreground mb-4">
                        You'll be redirected to Razorpay to complete the setup
                      </p>
                      <Button className="w-full">
                        <ExternalLink className="w-4 h-4 mr-2" />
                        Setup Razorpay
                      </Button>
                    </div>
                  </TabsContent>
                </Tabs>
                <DialogFooter>
                  <Button className="w-full" size="lg">Add Payment Method</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </CardHeader>
        <CardContent>
          {paymentMethods.length === 0 ? (
            <div className="text-center py-12">
              <CreditCard className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">No Payment Methods</h3>
              <p className="text-muted-foreground">
                Add a payment method to manage your subscriptions
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {paymentMethods.map((method) => (
                <div key={method.id} className="flex items-center justify-between p-4 border rounded-lg">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-8 bg-gradient-to-r from-blue-500 to-purple-500 rounded flex items-center justify-center">
                      <CreditCard className="w-5 h-5 text-white" />
                    </div>
                    <div>
                      <p className="font-semibold">•••• •••• •••• {method.last4}</p>
                      <p className="text-sm text-muted-foreground">
                        {method.brand} • Expires {method.expiry}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {method.isDefault && (
                      <Badge variant="secondary">Default</Badge>
                    )}
                    <Button variant="outline" size="sm">Edit</Button>
                    <Button variant="ghost" size="sm" className="text-red-600">
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Billing History */}
      <Card className="border-0 shadow-lg">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center gap-3">
            <FileText className="w-6 h-6" />
            Billing History
          </CardTitle>
          <CardDescription className="text-base">
            View and download your invoices and payment history
          </CardDescription>
        </CardHeader>
        <CardContent>
          {billingHistory.length === 0 ? (
            <div className="text-center py-12">
              <FileText className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">No Billing History</h3>
              <p className="text-muted-foreground">
                Your billing history will appear here once you have transactions
              </p>
            </div>
          ) : (
            <div className="overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[150px]">Invoice</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                    <TableHead className="w-[100px]">Status</TableHead>
                    <TableHead className="w-[100px] text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {billingHistory.map((invoice) => (
                    <TableRow key={invoice.id}>
                      <TableCell className="font-mono text-sm">{invoice.id}</TableCell>
                      <TableCell>{invoice.date}</TableCell>
                      <TableCell>{invoice.description}</TableCell>
                      <TableCell className="text-right font-semibold">${invoice.amount}</TableCell>
                      <TableCell>
                        <Badge 
                          variant={invoice.status === 'Paid' ? 'secondary' : 'destructive'}
                          className={invoice.status === 'Paid' 
                            ? 'bg-green-100 text-green-800' 
                            : 'bg-red-100 text-red-800'
                          }
                        >
                          {invoice.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="sm">
                          <FileText className="w-4 h-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Billing Address */}
      <Card className="border-0 shadow-lg">
        <CardHeader>
          <CardTitle className="text-2xl">Billing Address</CardTitle>
          <CardDescription className="text-base">
            Update your billing address for invoices and tax purposes
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <Label htmlFor="company">Company (Optional)</Label>
              <Input id="company" placeholder="Your Company" className="h-12" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="tax-id">Tax ID (Optional)</Label>
              <Input id="tax-id" placeholder="Tax Identification Number" className="h-12" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="address">Street Address</Label>
              <Input id="address" placeholder="123 Main Street" className="h-12" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="address2">Address Line 2</Label>
              <Input id="address2" placeholder="Apartment, suite, etc." className="h-12" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="city">City</Label>
              <Input id="city" placeholder="New York" className="h-12" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="state">State/Province</Label>
              <Input id="state" placeholder="NY" className="h-12" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="zip">Postal Code</Label>
              <Input id="zip" placeholder="10001" className="h-12" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="country">Country</Label>
              <Input id="country" placeholder="United States" className="h-12" />
            </div>
          </div>
          <div className="flex justify-end pt-6">
            <Button size="lg" className="px-8">
              <Check className="w-4 h-4 mr-2" />
              Save Billing Address
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Usage & Limits */}
      <Card className="border-0 shadow-lg">
        <CardHeader>
          <CardTitle className="text-2xl">Usage & Limits</CardTitle>
          <CardDescription className="text-base">
            Monitor your current usage against plan limits
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="text-center p-4 border rounded-lg">
              <div className="text-2xl font-bold text-primary">25</div>
              <div className="text-sm text-muted-foreground">Repositories</div>
              <div className="text-xs text-muted-foreground mt-1">of 100 limit</div>
              <div className="w-full bg-muted h-2 rounded-full mt-2">
                <div className="bg-primary h-2 rounded-full" style={{ width: '25%' }}></div>
              </div>
            </div>
            <div className="text-center p-4 border rounded-lg">
              <div className="text-2xl font-bold text-primary">1.2k</div>
              <div className="text-sm text-muted-foreground">API Calls</div>
              <div className="text-xs text-muted-foreground mt-1">of 10k limit</div>
              <div className="w-full bg-muted h-2 rounded-full mt-2">
                <div className="bg-primary h-2 rounded-full" style={{ width: '12%' }}></div>
              </div>
            </div>
            <div className="text-center p-4 border rounded-lg">
              <div className="text-2xl font-bold text-primary">3</div>
              <div className="text-sm text-muted-foreground">Team Members</div>
              <div className="text-xs text-muted-foreground mt-1">of 10 limit</div>
              <div className="w-full bg-muted h-2 rounded-full mt-2">
                <div className="bg-primary h-2 rounded-full" style={{ width: '30%' }}></div>
              </div>
            </div>
            <div className="text-center p-4 border rounded-lg">
              <div className="text-2xl font-bold text-primary">15GB</div>
              <div className="text-sm text-muted-foreground">Storage Used</div>
              <div className="text-xs text-muted-foreground mt-1">of 100GB limit</div>
              <div className="w-full bg-muted h-2 rounded-full mt-2">
                <div className="bg-primary h-2 rounded-full" style={{ width: '15%' }}></div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};